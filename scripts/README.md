# scripts

`python3 scripts/check_environment.py` でPython/Git/Node/npmの存在とバージョンを確認する。Nodeは22.9.0以上が必要。終了コード0は前提充足、1は不足または確認失敗。

設定・秘密値・ネットワーク状態は読み取らず、依存のインストールやOS設定変更も行わない。
