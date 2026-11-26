# Legend of Grimrock 2 日本語化パッチ Mac 用インストーラー

Windows 用の非公式日本語化パッチ「Legend of Grimrock 2 日本語化パッチ」(作者: Fugashi X) を、Mac 版 (Steam) の Legend of Grimrock 2 に当てるためのスクリプトです。

パッチ本体 (翻訳データとフォント) は Windows 用の配布物に入っているものをそのまま使います。このリポジトリに入っているのは Mac 用のインストーラーだけです。

## 必要なもの

- Steam 版 Legend of Grimrock 2 (Mac)。未改造の状態のもの
- Windows 用の日本語化パッチ (v1.0): <https://fugashi.net/mods/legend-of-grimrock-2> からダウンロードしてください
- Python 3
  - ターミナルで `python3 --version` と打ってバージョンが出れば入っています
  - 入っていない場合は `xcode-select --install` (Xcode コマンドラインツール) か Homebrew で入れてください

## インストール

1. <https://fugashi.net/mods/legend-of-grimrock-2> から Windows 用のパッチをダウンロードして展開します。中に `grimrock2_jp.patch` が入っています。
   以下の例では `~/Downloads/LoG2_JP_Patch_v1.0` に展開したものとします。
2. ゲームを終了します。
3. ターミナルでこのフォルダに移動します。

   ```sh
   cd ~/legend-of-grimrock-jp-patch-mac
   ```

4. (任意) 先にパッチを当てられるかを確かめます。何も書き換えません。

   ```sh
   python3 grimrock2_jp_mac.py check --patch ~/Downloads/LoG2_JP_Patch_v1.0/grimrock2_jp.patch
   ```

5. インストールします。

   ```sh
   python3 grimrock2_jp_mac.py install --patch ~/Downloads/LoG2_JP_Patch_v1.0/grimrock2_jp.patch
   ```

   「日本語化が完了しました。」と出れば完了です。

インストール時、元のファイルを `grimrock2.dat.orig` として `grimrock2.dat` と同じ場所に保存します (約 1GB)。

### ゲームを標準以外の場所に入れている場合

`grimrock2.dat` は標準では次の場所にあります。

```
~/Library/Application Support/Steam/steamapps/common/Legend of Grimrock 2/Legend of Grimrock 2.app/Contents/Resources/grimrock2.dat
```

別のライブラリフォルダに入れている場合は、`--dat` で `grimrock2.dat` のパスを指定してください。

```sh
python3 grimrock2_jp_mac.py install --patch <grimrock2_jp.patch のパス> --dat <grimrock2.dat のパス>
```

## アンインストール (英語版に戻す)

```sh
python3 grimrock2_jp_mac.py uninstall
```

`grimrock2.dat.orig` から元に戻します。Steam のライブラリでゲームを右クリック →「プロパティ」→「インストール済みファイル」→「ゲームファイルの整合性を確認」でも元に戻せます。

## 注意

- Steam がゲームを更新したり、整合性の確認をしたりすると、日本語化は消えます。その場合はもう一度 `install` を実行してください。
- アプリ (`.app`) の中のファイルを書き換えるため、macOS がゲームの起動を拒むことがあります。その場合は次のコマンドでアプリに署名し直してください。

  ```sh
  codesign --force --deep --sign - "$HOME/Library/Application Support/Steam/steamapps/common/Legend of Grimrock 2/Legend of Grimrock 2.app"
  ```

- Windows 版にある動作ログ (`ドキュメント\grimrock_jp_log.txt`) は、Mac では作られません。日本語表示には影響しません。
- Apple Silicon の Mac では、日本語化とは関係なく、ゲーム内の設定画面を開くと Lua のエラーで落ちる不具合が報告されています。設定は `~/Library/Application Support/Almost Human/Legend of Grimrock 2/grimrock.cfg` を直接編集して変えてください。

## しくみ

日本語化パッチは、`grimrock2.dat` の中のゲームスクリプト (LuaJIT バイトコード) の文字列を日本語に置き換え、日本語フォントを追加するものです。ゲームの実行ファイルには手を加えません。

Mac 版の `grimrock2.dat` は Windows 版とは少し中身が違います。そのため、元のパッチは Windows 版のファイルを前提にしたチェックで止まってしまいます。このスクリプトは書き換え対象のデータを1件ずつ調べて、次のように処理します。

| 種類 | 件数 | 処理 |
| --- | --- | --- |
| Windows 版と同じ中身のスクリプト | 76 | 元のパッチをそのまま当て、結果がパッチ作者の想定 (SHA-256) と一致することを確かめる |
| Windows 版と中身が違うスクリプト | 3 | 置き換える英語の文字列を Mac 版の中から探して日本語に差し替え、バイトコードを組み立て直す |
| 日本語フォント | 13 | そのまま追加する |

中身が違う3件は、キー設定画面、起動時のエラー表示と終了確認、メインメニューのスクリプトです。

すべてのデータを組み立てて確かめてから書き込むので、途中でエラーになっても `grimrock2.dat` は変更されません。

## 免責

本スクリプトは非公式のファンメイド作品です。Almost Human Ltd. および日本語化パッチの作者とは関係ありません。ご利用は自己責任でお願いします。
Legend of Grimrock 2 は Almost Human Ltd. の著作物・商標です。
