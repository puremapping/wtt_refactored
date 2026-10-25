# ITINERA 实跑验证报告

**验证日期：** 2026-09-17
**验证目的：** 确认 ITINERA 能否在本机跑通、能否改造用于本项目
**结论：** ✅ **核心算法全部跑通，可复用**

---

## 一、环境搭建结果

### 1.1 已安装并验证

**独立 venv**（`sandbox/ITINERA/.venv`，不污染 hermes 环境）

| 包 | 装上的版本 | ITINERA requirements 要求 |
| --- | --- | --- |
| numpy | 2.5.3 | 2.0.2 |
| pandas | 3.0.5 | 2.2.3 |
| scipy | 1.18.1 | 1.13.1 |
| networkx | 2.8.8 | 2.8.8 ✅ |
| shapely | 2.1.2 | 2.0.6 |
| geopandas | 1.1.4 | 1.0.1 |
| folium | ✓ | 0.18.0 |
| pulp | 3.3.2 | 2.9.0 |
| python_tsp | ✓ | 0.5.0 |
| openai | 3.14.1 | 1.54.3 |
| thefuzz | 0.22.1 | 0.22.1 ✅ |
| requests | 2.34.2 | 2.32.3 |
| xyconvert | 0.1.2 | 0.1.2 ✅ |

### 1.2 ⚠️ 安装过程的关键坑

**问题：`requirements.txt` 锁死的版本是给 Python 3.9 的，在 Python 3.13 上装不上。**

具体表现：
```
scipy==1.13.1 → 无 py3.13 wheel → 走源码编译
             → 缺 OpenBLAS (pkg-config not found)
             → ERROR: metadata-generation-failed
```

**解法：不锁版本安装**，让 pip 挑适配 3.13 的：
```bash
pip install numpy pandas scipy networkx shapely folium pulp python_tsp \
            openai thefuzz requests geopandas xyconvert \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**另一个坑：** PyPI 直连有 SSL 问题（`SSL: UNEXPECTED_EOF_WHILE_READING`），**必须用清华镜像**。

---

## 二、核心算法实跑结果

**测试脚本：** `sandbox/test_itinera_core.py`（不调 LLM，纯算法验证）

### 2.1 ✅ 数据加载

```
CSV  model/data/shanghai_zh.csv    形状 (20, 7)
     列: ['id','name','x','y','lon','lat','context']
NPY  model/data/shanghai_zh.npy    形状 (20, 1536)
```

**注意：`embedding` 维度是 1536** —— 这是 OpenAI `text-embedding-3-small` 的维度。
**GLM 的 embedding 维度不同（`embedding-3` 是 2048），换模型时 `.npy` 必须重算。**

### 2.2 ✅ 空间聚类（SpatialHandler）

**20 个上海 POI 聚成 4 簇：**

| 簇 | 数量 | 成员 |
| --- | --- | --- |
| 0 | 11 | 南京路步行街、上海邮政博物馆、外滩、乍浦路桥… |
| 1 | 6 | 武康大楼、愚园路、徐家汇公园、乌中市集… |
| 2 | 2 | Blue Bottle 咖啡、浦东美术馆 |
| 3 | 1 | 大学路 |

**空间合理性判断：** ✅ 簇 0 是外滩/南京路核心区，簇 1 是法租界/徐汇区，簇 2 是浦东——**地理上完全站得住**，说明聚类算法真实生效。

### 2.3 ✅ TSP 路径排序（模拟退火）

**输出路线：**
```
南京路步行街 → 上海四行仓库 → 思南公馆 → 徐家汇公园 → 武康大楼
→ 乌中市集 → 静安寺 → 愚园路 → Blue Bottle → M50创意园
→ 鲁迅公园 → 大学路 → 山阴路 → 上海邮政博物馆 → 四川路桥
→ 乍浦路桥 → 外白渡桥 → 浦东美术馆 → 外滩 → 上海和平饭店
```
总距离 37818.2（投影坐标单位）

**合理性判断：** ✅ 路线在空间上连续（桥梁群连成一段、外滩收尾），符合实际游览动线。

### 2.4 ✅ GCJ-02 → WGS-84 坐标转换

```
南京路步行街   GCJ02(121.484593,31.237542) → WGS84(121.480106,31.239511)
上海邮政博物馆  GCJ02(121.484801,31.244392) → WGS84(121.480314,31.246360)
外滩         GCJ02(121.490603,31.237770) → WGS84(121.486138,31.239758)
```

**这对本项目很重要：** 高德返回的是 GCJ-02，若前端用 Leaflet + OpenStreetMap（WGS-84），**必须做这个转换**，否则会有几十米偏移。ITINERA 自带 `xyconvert` 解决这个问题。

---

## 三、GLM-4 兼容性验证

**测试脚本：** `sandbox/test_glm_compat.py`

### 3.1 ✅ 结论：只改一个文件

`proxy_call.py`（34 行）是唯一的 LLM 接口层：

```python
class OpenaiCall:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    def chat(self, messages, model="gpt-3.5-turbo-1106", temperature=0): ...
    def embedding(self, input_data): ... model="text-embedding-3-small"
```

**改造方案：**
```python
self.client = OpenAI(
    api_key=os.getenv("GLM_API_KEY"),
    base_url="https://open.bigmodel.cn/api/paas/v4/",   # ← 加这行
)
# model 名改为 glm-4-flash
```

### 3.2 ⚠️ openai SDK 版本差异

| 项 | ITINERA 要求 | 实测装上 |
| --- | --- | --- |
| openai | 1.54.3 | **3.14.1** |

**验证结果：`base_url` 参数在 3.x 中依然存在**，调用签名 `client.chat.completions.create(model=..., messages=..., temperature=...)` 也兼容。
→ **大版本跃迁未破坏兼容性**，无需降级。

### 3.3 ⚠️ embedding 维度问题

- ITINERA 的 `.npy` 是 **1536 维**（OpenAI `text-embedding-3-small`）
- GLM 的 `embedding-3` 是 **2048 维**
- **两者的向量不可混用** → 换 GLM 时 `.npy` 必须用 GLM 的 embedding 重新生成

---

## 四、换北京数据的完整路径

**代码无需改动**，`main.py --city beijing` 会自动找 `beijing_zh.csv` / `beijing_zh.npy`。

### 需要准备两个文件

**1. `model/data/beijing_zh.csv`**

列格式（严格）：
```csv
id,name,x,y,lon,lat,context
7973,南京路步行街,13523603.01635883,3663637.0235004686,121.48459285959999,31.237541636,"南京路步行街, 黄浦区, 南京路步行街是上海著名的商业步行街……"
```

| 列 | 说明 | 我们的数据源 |
| --- | --- | --- |
| `id` | 唯一整数 ID | 自行编号 |
| `name` | POI 名称 | ✅ 平台「北京市等级景区信息」有 212 条 |
| `x`, `y` | **投影坐标**（Web Mercator 量级） | 需从经纬度转换 |
| `lon`, `lat` | **GCJ-02 经纬度** | ⚠️ **需高德地理编码** |
| `context` | 自然语言描述（用于 embedding） | 可用 `name + 区 + 简介` 拼接 |

**2. `model/data/beijing_zh.npy`**

- `context` 列的 embedding
- **行序必须与 CSV 一致**
- 维度取决于所用 embedding 模型

### ⚠️ 发现的字段不一致坑

`search.py` 的自动生成 embedding 分支期待 `address` + `desc` 两列：
```python
context = data['name'] + "，地址是" + data['address'] + "，" + data['desc']
```
但样例 CSV 只有单列 `context`。

**结论：不能依赖它自动生成 `.npy`，必须自己预先算好。**

---

## 五、实际运行的前置条件

| 项 | 状态 |
| --- | --- |
| 依赖 | ✅ 全部装好 |
| 核心算法 | ✅ 跑通 |
| LLM 接口 | ✅ 确认可切 GLM-4 |
| **GLM API key** | ❌ **未设置**（`GLM_API_KEY`） |
| **北京数据** | ❌ 未准备（需地理编码 + embedding） |

**下一步要跑通完整流程，需要：**
1. 智谱 GLM API key
2. 用高德把 212 个景区编码成坐标（212 次配额，5000/日限额内）
3. 用 GLM embedding 生成 `.npy`

---

## 六、对项目的结论

### 可直接复用的部分

| 组件 | 文件 | 复用方式 |
| --- | --- | --- |
| **空间聚类** | `spatial.py` | 直接用（实测跑通） |
| **TSP 排序** | `spatial.py` | 直接用（实测跑通） |
| **坐标转换** | `xyconvert` 包 | 直接用（实测跑通） |
| **POI 向量检索** | `search.py` | 直接用（余弦相似度 + 负向需求加权） |
| **Prompt 模板** | `all_prompts.py` | 改用 GLM 后直接搬 |
| **时间→参数映射表** | `itinera.py` |

**那张映射表原文：**
```python
# (hours) → (min_clusters, poi_num, distance_thresh)
TIME2NUM = {1:(1,3,2000), 2:(1,5,3000), 3:(2,7,4000), 4:(2,9,5000),
            5:(3,11,6000), 6:(3,13,7000), 7:(4,15,8000), 8:(4,17,9000)}
```

### 注意事项

- ⚠️ **License: GPL-3.0**，直接复用代码的衍生作品需同样开源
- ⚠️ 其 POI 数据仅 20 条演示样例，**不是数据集**
- ⚠️ README 说作者联系方式在 LICENSE 里，商用需联系作者

---

## 附：验证产物

| 文件 | 说明 |
| --- | --- |
| `sandbox/ITINERA/` | 克隆的仓库（含 `.venv`） |
| `sandbox/test_itinera_core.py` | 核心算法测试（4 项全过） |
| `sandbox/test_glm_compat.py` | GLM 兼容性测试 |

**验证方法局限：** 未调用真实 LLM（无 API key），因此「端到端生成行程」这一步未实测；核心算法与接口兼容性均已验证。
