# Windowsホスト

現行配布候補は **0.6.0-rc.1**。Wi-Fi固定でAtomS3Rの質問をGemini Liveへ中継します。声のPC試聴・採用・一覧選択・保存に対応します。

- [利用手順](README.ja.md)
- [RC1の成果物・検証](../docs/RELEASE_CANDIDATE_0_6_0_2026-10-21.md)
- [開発・再開](../docs/RESUME.md)
- [旧Windows開発記録](../docs/archive/2026-10-21/rc1-before-compaction/desktop/README.md)

ソースはこのフォルダ、中継はserver/。配布は`python desktop/build_windows.py --node <Node v24.15.0のパス>`で作成し、クリーンステージ・秘密値検査・最終EXE自己診断を行います。配布物へ個人設定・キー・音声を含めません。
