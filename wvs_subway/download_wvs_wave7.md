# 自行获取 WVS Wave 7

完整数据路径使用 World Values Survey, Round Seven, Country-Pooled Datafile Version 6.0。

1. 前往 [WVS 官方 Wave 7 页面](https://www.worldvaluessurvey.org/WVSDocumentationWV7.jsp)。
2. 由数据使用者本人填写下载信息并接受 Conditions of Use，下载 CSV ZIP。
3. 将 ZIP 放在本目录的 `data/raw/`；该路径已被审稿包的 `.gitignore` 排除。文件名可以是官方原名，也可以带下载编号前缀。
4. 在审稿包根目录运行：

   ```bash
   python scenario/wvs_subway/prepare_wvs_population.py \
     --source scenario/wvs_subway/data/raw/F00011356-WVS_Cross-National_Wave_7_csv_v6_0.zip \
     --output local_inputs/wvs_profiles.jsonl
   ```

默认生成 64 名档案，按完整清洗后的 WVS 来源池计算标准化值，再无放回抽样。若需要更多人，可添加 `--population-size N`；超过来源记录数时必须显式使用 `--sampling-mode with_replacement`，这会重复抽取来源行并生成不同的智能体 ID。

审稿包不附带 WVS 原始 ZIP 或由其生成的档案。请遵守 WVS 的下载与使用条件，并引用：Haerpfer et al. (eds.), World Values Survey: Round Seven, Country-Pooled Datafile Version 6.0, DOI: [10.14281/18241.24](https://doi.org/10.14281/18241.24)。
