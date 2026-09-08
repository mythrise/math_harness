"""Train-only selection, interpretable backbone, optional residual expert, calibration.
These CPU algorithms are real implementations, not stand-ins claiming to run TabPFN.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.linear_model import LinearRegression, Ridge, HuberRegressor, LogisticRegression
from sklearn.model_selection import KFold, GroupKFold, TimeSeriesSplit, StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, log_loss
from .algopt import array


class ResidualRegressor(RegressorMixin, BaseEstimator):
    """Cross-fitted residual specialist; alpha=0 preserves the backbone exactly.
    Nested fitting only consumes supplied training rows. The inner residual folds
    must match dependence; for groups/time use the plain portfolio without this
    IID-only candidate. This method is a research candidate, not global promotion.
    """
    def __init__(self, alpha=.5, seed=0): self.alpha=alpha; self.seed=seed
    def fit(self,X,y):
        X,y=array(X,2),array(y,1)
        if len(X)!=len(y) or len(y)<12 or not 0<=self.alpha<=1: raise ValueError('Residual fit contract')
        self.backbone_=make_pipeline(StandardScaler(),Ridge(alpha=1.)).fit(X,y)
        self.residual_=None
        if self.alpha == 0: return self
        oof=np.empty(len(y))
        for tr,va in KFold(3,shuffle=True,random_state=self.seed).split(X):
            m=make_pipeline(StandardScaler(),Ridge(alpha=1.)).fit(X[tr],y[tr]);oof[va]=m.predict(X[va])
        self.residual_=HistGradientBoostingRegressor(max_iter=60,max_leaf_nodes=7,min_samples_leaf=10,
                           l2_regularization=1.,early_stopping=False,random_state=self.seed).fit(X,y-oof)
        return self
    def predict(self,X):
        base=self.backbone_.predict(X)
        return base if self.residual_ is None else base+self.alpha*self.residual_.predict(X)


def folds_for(X,y,*,kind='iid',groups=None,n_splits=3,seed=0,classification=False):
    if n_splits<2: raise ValueError('At least two folds required')
    if kind=='group':
        if groups is None or len(groups)!=len(y): raise ValueError('Groups required')
        folds=list(GroupKFold(n_splits).split(X,y,groups))
    elif kind=='time':
        folds=list(TimeSeriesSplit(n_splits).split(X))
    elif kind=='iid':
        splitter=StratifiedKFold(n_splits,shuffle=True,random_state=seed) if classification else KFold(n_splits,shuffle=True,random_state=seed)
        folds=list(splitter.split(X,y))
    else: raise ValueError('Unknown dependence kind')
    for tr,va in folds:
        if set(tr)&set(va): raise ValueError('Fold overlap')
        if kind=='time' and max(tr)>=min(va): raise ValueError('Noncausal fold')
        if kind=='group' and set(np.asarray(groups)[tr])&set(np.asarray(groups)[va]):raise ValueError('Group leakage')
    return folds


@dataclass
class FittedPortfolio:
    estimator: object
    report: dict
    def predict(self,X):
        X=array(X,2,'predict X')
        return np.asarray(self.estimator.predict(X))
    def predict_proba(self,X):
        if not hasattr(self.estimator,'predict_proba'):raise ValueError('Not a probabilistic classifier')
        return self.estimator.predict_proba(array(X,2))


def fit_tabular(X,y,*,task='regression',kind='iid',groups=None,seed=0,n_splits=3,
                include_residual=False,residual_gate='all_folds',max_candidates=5,max_fits=36,min_gain=.02):
    """Select on inner CV only; no calibration or test labels are accepted by API.
    Refit chosen model on *training* data. Frozen min_gain is a pragmatic selection
    hurdle, not a confidence bound or a guarantee against test-set regressions.
    """
    X=array(X,2,'X'); y=np.asarray(y)
    if X.shape[0]!=len(y) or X.shape[1]==0 or y.ndim!=1 or len(y)<24:raise ValueError('Tabular shapes/sample size')
    if task not in ('regression','classification'):raise ValueError('Unknown task')
    if not 1<=max_candidates<=8 or max_fits<1 or not 0<=min_gain<1:raise ValueError('Selection budget')
    if task=='regression':
        y=array(y,1,'y')
        models=[('ols',make_pipeline(StandardScaler(),LinearRegression())),
                ('ridge',make_pipeline(StandardScaler(),Ridge(alpha=1.))),
                ('huber',make_pipeline(StandardScaler(),HuberRegressor(max_iter=500))),
                ('hist_gbdt',HistGradientBoostingRegressor(max_iter=80,max_leaf_nodes=15,early_stopping=False,random_state=seed))]
        if include_residual and kind=='iid':models.append(('crossfit_residual',ResidualRegressor(.5,seed)))
    else:
        y=array(y,1,'y')
        if len(np.unique(y))<2:raise ValueError('At least two classes required')
        models=[('logistic',make_pipeline(StandardScaler(),LogisticRegression(max_iter=500))),
                ('hist_gbdt',HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,early_stopping=False,random_state=seed))]
    if residual_gate not in ('all_folds','disabled'):raise ValueError('Unknown residual admission gate')
    models=models[:max_candidates];folds=folds_for(X,y,kind=kind,groups=groups,n_splits=n_splits,seed=seed,classification=task=='classification')
    # Include the internal crossfit fits of the residual estimator in the fit budget.
    counts={name:(5 if name=='crossfit_residual' else 1) for name,_ in models}
    fits_required=sum(counts[n]*len(folds) for n,_ in models)+max(counts.values())
    if fits_required>max_fits:raise ValueError(f'Fit budget exceeded: requires at most {fits_required}, supplied {max_fits}')
    rows=[];fits=0
    for name,model in models:
        scores=[]
        for tr,va in folds:
            est=clone(model).fit(X[tr],y[tr]);fits+=counts[name]
            if task=='regression':score=mean_squared_error(y[va],est.predict(X[va]))
            else:
                if set(np.unique(y[tr]))!=set(np.unique(y)):raise ValueError('Training fold missing class')
                score=log_loss(y[va],est.predict_proba(X[va]),labels=est.classes_)
            if not np.isfinite(score):raise ValueError('Nonfinite CV loss')
            scores.append(float(score))
        rows.append(dict(id=name,loss=float(np.mean(scores)),fold_losses=scores))
    best=min(range(len(rows)),key=lambda i:(rows[i]['loss'],i))
    # Require a substantive relative gain; the original baseline remains available.
    selected=best if rows[best]['loss']<rows[0]['loss']*(1-min_gain) else 0
    gate_passed=None
    if rows[selected]['id']=='crossfit_residual' and residual_gate=='all_folds':
        classical=min((i for i in range(len(rows)) if rows[i]['id']!='crossfit_residual'),key=lambda i:rows[i]['loss'])
        gate_passed=bool(np.all(np.asarray(rows[selected]['fold_losses']) < np.asarray(rows[classical]['fold_losses'])*(1-min_gain)))
        if not gate_passed:selected=classical if rows[classical]['loss']<rows[0]['loss']*(1-min_gain) else 0
    model=clone(models[selected][1]).fit(X,y);fits+=counts[models[selected][0]]
    return FittedPortfolio(model,dict(selected=models[selected][0],baseline=models[0][0],scores=rows,
        fits=fits,fit_budget=max_fits,dependence=kind,calibration_used=False,test_used=False,
        residual_eligible=kind=='iid',residual_gate=residual_gate,residual_gate_passed=gate_passed,status='INNER_CV_SELECTED_NOT_EXTERNALLY_PROMOTED',
        fold_indices=[{'train':tr.tolist(),'validation':va.tolist()} for tr,va in folds]))


def conformal_interval(predictions,calibration_y,calibration_predictions,*,alpha=.1,exchangeable=False):
    """Split-conformal absolute residual interval. Calibration must be untouched by
    fitting/selection; exchangeability is a user responsibility, not a detected fact.
    For k>n the mathematically valid threshold is infinite, not the largest residual.
    """
    if not exchangeable:raise ValueError('Exchangeability not attested; no split-conformal guarantee')
    p,y,pc=array(predictions,1),array(calibration_y,1),array(calibration_predictions,1)
    if y.shape!=pc.shape or len(y)==0 or not 0<alpha<1:raise ValueError('Calibration contract')
    scores=np.sort(np.abs(y-pc));k=math.ceil((len(y)+1)*(1-alpha))
    q=float(scores[k-1]) if k<=len(y) else np.inf
    return dict(lower=p-q,upper=p+q,quantile=q,n_calibration=len(y),
        guarantee='MARGINAL_UNDER_EXCHANGEABILITY_AND_UNTOUCHED_CALIBRATION',
        conditional_coverage_guarantee=False)


def forecast_candidate(history,horizon,method,season):
    y=array(history,1,'history')
    if len(y)<3 or not isinstance(horizon,int) or horizon<1 or not isinstance(season,int) or season<1:
        raise ValueError('Forecast horizon/history/season')
    if method=='naive':return np.repeat(y[-1],horizon)
    if method=='linear':
        t=np.arange(len(y));co=np.polyfit(t,y,1);return np.polyval(co,np.arange(len(y),len(y)+horizon))
    if method=='seasonal':
        if len(y)<season:raise ValueError('Insufficient seasonal context')
        return np.resize(y[-season:],horizon)
    if method=='seasonal_residual':
        if len(y)<3*season:raise ValueError('Need three seasonal cycles')
        # Fixed recent trend + seasonal residual. No future values, no large model.
        yy=y[-min(len(y),8*season):];t=np.arange(len(yy));slope=np.median((yy[season:]-yy[:-season])/season)
        residual=yy-slope*t
        by_phase=np.array([np.mean(residual[i::season]) for i in range(season)])
        tt=np.arange(len(yy),len(yy)+horizon)
        return slope*tt+by_phase[tt%season]
    if method=='ridge_lags':
        lag=min(2*season,24)
        if len(y)<lag+12:raise ValueError('Not enough rows for lagged fit')
        X=np.array([y[i-lag:i] for i in range(lag,len(y))]);target=y[lag:]
        model=make_pipeline(StandardScaler(),Ridge(alpha=1.)).fit(X,target)
        series=y.tolist()
        for _ in range(horizon):series.append(float(model.predict(np.array(series[-lag:])[None,:])[0]))
        return np.asarray(series[-horizon:])
    raise ValueError('Unknown forecast method')


def forecast_portfolio(history,horizon,*,season=1,origins=3,max_fits=16,min_gain=.02):
    y=array(history,1)
    if not isinstance(horizon,int) or horizon<1 or not isinstance(origins,int) or origins<2 or not 0<=min_gain<1:
        raise ValueError('Invalid rolling validation contract')
    methods=['linear','naive','seasonal','seasonal_residual','ridge_lags']
    min_train=max(3*season, min(2*season,24)+12, 16)
    starts=[len(y)-horizon*j for j in range(origins,0,-1)]
    if starts[0]<min_train:raise ValueError('Insufficient history for disjoint rolling-origin selection')
    if len(methods)*origins+1>max_fits:raise ValueError('Forecast fit budget exceeded')
    rows=[]
    for method in methods:
        losses=[float(np.mean(np.abs(y[t:t+horizon]-forecast_candidate(y[:t],horizon,method,season)))) for t in starts]
        rows.append(dict(id=method,mae=float(np.mean(losses)),origin_losses=losses))
    best=min(rows,key=lambda r:r['mae'])
    chosen=best['id'] if best['mae']<rows[0]['mae']*(1-min_gain) else rows[0]['id']
    pred=forecast_candidate(y,horizon,chosen,season)
    if not np.isfinite(pred).all():raise ValueError('Nonfinite forecast')
    return dict(prediction=pred,selected=chosen,origin_starts=starts,scores=rows,
                fits=len(methods)*origins+1,test_used=False,
                scope='UNIVARIATE_REGULAR_TIME_NO_EXOGENOUS_INPUT; NO_COVERAGE_GUARANTEE')
