# 交给 Codex：以用户上传 Search API Reference 为准落实 Exa 配置 R2

请在我的 `mythrise/math_harness` 当前实际工作树中实施，不要只回答配置建议。先读取AGENTS.md和当前相关测试；保护未提交更改，不强制回退旧版本。本包依据与代码文件摘要见sources.json与specs中的repository_read_evidence。

**本包取代上一版 Exa 配置交接包，但不是已经修改好的harness。**

## 要达到的目标

将Exa作为控制器管理的科研证据服务：抽象查询→支持调查→建模假设→独立反例调查→逐来源精读→科学审查→实际假设检验→论文引用。

必须保留：get_exa_api_key及其环境变量优先/本地私有加载；Claude/GPT双席和故障接管；既有评测器和负控制；MOSAIC与OurWork；国赛真实人工签核；旧工作区证据不可改写。不要让每个Agent自行绕过账本联网，不自动改Codex MCP，不自动commit/push。

## 三层文件分别处理

1. `configs/exa-modeling-compatible.json`：现有字段80次尝试/6条/45秒，其他值沿用exa-resilient。用户已指定的模型或限额不能覆盖。
2. `specs/exa-research-policy.proposed.json`：本地策略设计，需你实现schema、明确加载入口与控制器接线；未经实现不能传给现有config或Exa。
3. `examples/raw-exa-requests.json`：endpoint/public_headers/body；**只把body发为JSON请求体**。public_headers没有鉴权；它只能由现有加载器在HTTP调用前注入，不记入日志。

## 先核对现行文件

检查literature.py、controller.py、credentials.py、review_board.py、intake.py、contracts.py和tests。阅读用户附件Search API Reference及官方Contents文档。以已验证接口冻结能力，禁止以搜索引擎的旧摘要推翻附件的新字段。

新策略使用Bearer；旧运行可显式保留x-api-key兼容模式。不得展示真实密钥、同时发两种鉴权、在401后擅自换认证方式。保留urllib/httpx原始REST则JSON使用camelCase；**只有使用Exa Python SDK时**才把参数及嵌套contents映射为snake_case。不要为这次任务强行替换SDK。

## 必须实现的协议细节

- 类型按附件auto/fast/instant/deep-lite/deep/deep-reasoning；默认auto；stream=false。
- 学术category=publication；代码/官方API查询不带publication。遇明确不支持时仅可走已冻结、已授权的无category学术补充，并记录。未知400/422不得无限重试。
- /search中的text/highlights/summary只在contents内；/contents则在顶层。
- 禁止useAutoprompt、tokensNum、numSentences、highlightsPerUrl、livecrawl、includeUrls/excludeUrls等过时或不存在参数。
- 常规发现每来源2000字符、反方3000；关键正文24000，必要时60000。同步修改normalize的10000字符硬截断，保留阅读范围；命中限制不等于读完整篇。
- Dynamic Highlights新增独立可选profile，生产默认关闭。每次dynamic=true都加`Exa-Beta: dynamic-highlights-2026-08-28`，且摘录对象不能含maxCharacters。不能编造动态总字符或token预算字段；动态只针对本次搜索结果，不是全工作流预算。
- 只有显式opt-in＋真实能力检查后允许广度发现使用动态模式，反方/关键引用继续逐来源模式与原文核验。无摘录结果保留元数据，不能等同不相关。
- 预览不可用时，仅按已授权范围改用稳定摘录；保留原请求与退化事件，计入最多3次总尝试。401/403、预算耗尽、有效科学FAIL不允许这样退化。
- beta版本/模式加入非秘密缓存身份与回执。请求头有认证信息，严禁整体记录headers；只保存Content-Type与Exa-Beta等明确白名单字段。
- deep升级默认关闭、最多2次；outputSchema用本包的4个平坦字段，最多2层/10属性，不自行定义citation。保存results、output.content、output.grounding；按字段存在解析，不只在type=deep分支解析。
- 附件关于outputSchema支持所有type的正文与“deep search only”示例注释不一致：记录这一点，以显式参数说明设计并用接口测试确认，不靠注释写死。合成内容只做研究导航，不能进原文quote或直接批准假设。
- additionalQueries仅deep变体使用，最多2条，分别隐私检查。systemPrompt由控制器生成；所有附加文本都不能夹带题面、数据或标识。

## 预算、故障与恢复

80是每题真实HTTP尝试的上限而不是80篇论文或美元预算。所有重试、能力检查和模式退化计入原子预算。并发2、共享软QPS1、普通45秒/deep90秒，livecrawlTimeout=15000毫秒。用独立通信随机源做有界退避，遵循Retry-After，不影响数学实验随机轨迹。

逐URL处理/contents的200内失败，先保留成功，只重试明确失败。401/403等待认证；空结果记EMPTY并换查询角度，而非原样循环或宣称不存在。关键证据缺失阻断依赖门禁，不阻止无依赖节点。无法确认在途请求结果时保留UNKNOWN并显式协调，不能承诺外部API exactly-once计费。

新工作区冻结UTC研究截止、策略/解析器/能力版本及授权。所有日期从截止计算；理论和反例不设开始年份。原始文献出版日是估计，需要版本核验，未知不能假造。恢复使用原快照不联网刷新，跨工作区TTL和Exa maxAgeHours分开处理；新证据使依赖审查/签核失效。保留负证据和实际成本；费用缺失记UNKNOWN。

## 科学与权限门禁

保持按hypothesis_id或关键claim_id关联检索，不按文献数量决定充分性。支持与反方分别提问；没有搜到反例不是证明。经验假设必须执行测试。检查引文原文位置与语义，译文/摘要不冒充原文，镜像去重，结果未精读标注覆盖范围。

正式竞赛按原有授权边界审批抽象查询。审批应绑定query/profile/domain/time/fetch范围，不能借模式回退扩大权限。动态模式不削弱内容核验或原题外发检查。数值容器继续断网，操作员批准不能由Agent代签。

## 参考代码与验收

reference/request_contract.py是本策略所需请求子集的离线形状校验参考，不是完整Exa客户端，不负责DNS防护、预算、身份隔离、网络执行或回复语义验证。可复用逻辑，但必须接入真正Controller并新增严格policy schema；不要把离线测试误称真实鉴权成功。

先运行本包离线测试，再实施ACCEPTANCE_TESTS.md中的当前仓库回归与错误注入。已有认证且获得相应运行许可时，做最多8次公开方法资料烟测，禁止使用赛题正文；先稳定请求，再经显式开启测试动态预览。真实成功/失败/未执行分栏，费用、请求ID与失败分类脱敏记录。

最后在新工作区跑原有完整demo到实际PDF和支撑包，并恢复一次，验证不重复已完成查询、审查和实验。fixture、真实Exa、真实模型、实际数值和排版分别报告。缺环境记NOT_RUN，不编造通过。

交付：真实diff、解析后的生效配置、脱敏请求与回执、测试命令和结果、迁移/回滚说明、未测边界。不自动推送GitHub。
