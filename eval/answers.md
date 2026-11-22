# Answer evaluation

Answer model: `openai/gpt-oss-20b` · judge: `qwen/qwen3.8-27b` · retrieval: hybrid + rerank, non-French questions translated to French for search · 2026-11-22

| Questions | n | Correct | Cites a right article | Refused | Right article in top 5 |
|---|---|---|---|---|---|
| Answerable (fr) | 26 | 77% | 81% | 19% | 96% |
| Answerable (en) | 8 | 75% | 75% | 25% | 100% |
| Answerable (ar) | 8 | 62% | 88% | 12% | 100% |
| **Answerable (all)** | 42 | **74%** | 81% | 19% | 98% |
| **Unanswerable** (should refuse) | 6 | **83%** refused correctly | – | 83% | – |

## Wrong or refused

| Question | Answer given | Judge |
|---|---|---|
| fr11 | Je n'ai pas trouvé la réponse dans les circulaires indexées. |  |
| fr12 | Je n'ai pas trouvé la réponse dans les circulaires indexées. |  |
| fr14 | Je n'ai pas trouvé la réponse dans les circulaires indexées. |  |
| fr15 | Le taux de provisionnement standard pour la promotion immobilière est de 6,75 %. [5]  
L’ancienne valeur était de 30 %. [2] | The reference answer states the standard provisioning rate is 30%. The system answer claims the current rate is 6.75% an |
| fr24 | Je n'ai pas trouvé la réponse dans les circulaires indexées. |  |
| fr25 | Je n'ai pas trouvé la réponse dans les circulaires indexées. |  |
| en01 | I could not find the answer in the indexed circulars. |  |
| en04 | I could not find the answer in the indexed circulars. |  |
| ar01 | لم أجد الإجابة في المناشير المفهرسة. |  |
| ar05 | المقاييس المحددة لقروض زراعة الحبوب هي كما يلي:  
- للقمح الصب والين والبقول، 1 هكتار = 1255 دينار، 2 هكتار = 1750 دينار.  
- للشعير، 1 هكتار = 1020 دينار، 2 هك | The reference answer states that the criteria are defined by specific circulars (notably 2022-07) and does not list spec |
| ar08 | الشروط التي تُستثنى من تمويل توريد المنتجات غير ذات الأولوية هي:  
- استيراد المنتجات في إطار المشتريات العامة لصالح الدولة، والمؤسسات والشركات العامة، والسلطات | The reference answer states that the conditions are defined by Circular 2017-09 as amended by 2018-01. The system answer |
| na05 | Cash payments are subject to a threshold of 10 000 dinars, or the equivalent of 5 000 foreign banknotes, beyond which additional due‑diligence is required. [1] |  |
