# 002 区划版本与换算草案

在001基础上新增三张表（仍由SQLAlchemy metadata创建；生产环境应改为真实迁移）：

- `division_versions`：`code`唯一，`is_current`标记现行区划（全表至多一个，由服务层维护）。
- `division_ratios`：相邻版本间的拆并比例，唯一约束`uq_ratio(from_version_id,to_version_id,from_zone,to_zone)`；`revision`为边级修订号，整边替换时+1。同一旧区划的全部去向比例合计必须为1（人口守恒），由换算时校验。
- `conversion_drafts`：批次的换算草案。`payload`保存来源人口、转移矩阵、换算结果、所用路径与边；`fingerprint`为所用比例行（含修订号）的SHA256。`status`：draft/stale/published。

并发口径：修订比例在同一事务内替换整边并把依赖草案置为stale；发布草案先按比例行加锁重算指纹，再校验并替换整套目标边际。历史`weight_runs`结果不回写。
