"""Shortest paths with checked heuristic hints. No learned hard edge deletion."""
from __future__ import annotations
import heapq
import numpy as np
from .algopt import array


def shortest_path(n,edges,start,goal,*,heuristic=None):
    if (isinstance(n,bool) or not isinstance(n,int) or n<=0
        or any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<n for i in (start,goal))):
        raise ValueError('Node IDs must be integers in range')
    clean=[];adj=[[] for _ in range(n)]
    for edge in edges:
        if len(edge)!=3:raise ValueError('Edge must be (from,to,cost)')
        u,v,w=edge
        if any(isinstance(i,bool) or not isinstance(i,(int,np.integer)) or not 0<=i<n for i in (u,v)):
            raise ValueError('Invalid endpoint')
        w=float(w)
        if not np.isfinite(w):raise ValueError('Finite edge weights required')
        clean.append((int(u),int(v),w));adj[u].append((int(v),w))
    d=[float('inf')]*n;d[start]=0.;parent=[None]*n;expanded=0
    h=np.zeros(n);accepted=False
    if heuristic is not None:
        proposal=array(heuristic,1,'heuristic')
        if proposal.shape!=(n,):raise ValueError('Heuristic shape')
        # Strict floating comparisons, no tolerance that might permit inadmissible h.
        accepted=bool(proposal[goal]==0 and all(proposal[u]<=w+proposal[v] for u,v,w in clean))
        if accepted:h=proposal
    if any(w<0 for _,_,w in clean):
        method='bellman_ford';accepted=False
        for _ in range(n-1):
            changed=False
            for u,v,w in clean:
                if d[u]+w<d[v]:d[v]=d[u]+w;parent[v]=u;changed=True
            expanded+=1
            if not changed:break
        if any(d[u]+w<d[v] for u,v,w in clean):
            return dict(status='REACHABLE_NEGATIVE_CYCLE',path=[],distance=None,heuristic_accepted=False,method=method)
    else:
        method='verified_astar' if accepted else 'dijkstra'
        heap=[(float(h[start]),0.,start)]
        while heap:
            _,cost,u=heapq.heappop(heap)
            if cost!=d[u]:continue
            expanded+=1
            if u==goal:break
            for v,w in adj[u]:
                nc=cost+w
                if nc<d[v]:
                    d[v]=nc;parent[v]=u;heapq.heappush(heap,(float(nc+h[v]),nc,v))
    if not np.isfinite(d[goal]):
        return dict(status='UNREACHABLE',path=[],distance=None,heuristic_accepted=accepted,method=method,expanded=expanded)
    path=[];node=goal
    for _ in range(n+1):
        path.append(node)
        if node==start:break
        node=parent[node]
        if node is None:raise RuntimeError('Broken predecessor certificate')
    else:raise RuntimeError('Predecessor cycle')
    path.reverse()
    # Independent path-cost check (parallel edges retain the cheapest edge).
    edge_cost={}
    for u,v,w in clean:edge_cost[(u,v)]=min(edge_cost.get((u,v),np.inf),w)
    cost=sum(edge_cost[u,v] for u,v in zip(path,path[1:]))
    if not np.isclose(cost,d[goal],rtol=1e-10,atol=1e-12):raise RuntimeError('Path cost mismatch')
    return dict(status='PATH_FOUND',path=path,distance=float(cost),method=method,
                heuristic_accepted=accepted,expanded=expanded,
                certificate='ALGORITHMIC_SHORTEST_PATH_UNDER_DECLARED_WEIGHTS; FLOATING_ARITHMETIC')
