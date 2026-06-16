# ミーウニトア（モニターレイアウト切り替えツール）

*[English README here](README.en.md)*

GNOME のモニターレイアウト（位置・解像度／リフレッシュレート・スケール・回転・
プライマリディスプレイ）を保存し、トップバーのメニュー・コマンドライン・
キーボードショートカット、またモニターの抜き差し時に自動で切り替えるための
ツールです。

通常のツール（`xrandr`・`autorandr`・`wlr-randr`）が動作しない **GNOME Wayland**
でも、mutter の `org.gnome.Mutter.DisplayConfig` D-Bus インターフェースを直接
呼び出すことで動作します。

## 構成

| リポジトリ内のパス | インストール先 | 内容 |
|---|---|---|
| `bin/monitor-layout` | `~/.local/bin/monitor-layout`（および `ml` エイリアス） | D-Bus 経由でレイアウトを保存／適用する Python 製 CLI |
| `extension/miiunitoa@meeksi39/` | `~/.local/share/gnome-shell/extensions/miiunitoa@meeksi39/` | GNOME Shell 拡張機能。保存済みレイアウトを一覧表示し、適用するトップバーメニュー |

保存したレイアウトは `~/.config/monitor-layouts/` に JSON として保存されます
（レイアウト 1 つにつき 1 ファイル、例: `work.json`）。これは**ユーザーデータ**で
あり、git では管理しません。

## 必要なもの

- **Wayland** 上の GNOME Shell 45〜50
- PyGObject 付きの Python 3（`python3-gobject` / `pygobject`）— GNOME 環境では
  通常すでにインストールされています
- `~/.local/bin` が `PATH` に含まれていること

## インストール

```sh
git clone git@github.com:Meeksi39/miiunitoa.git ~/miiunitoa
cd ~/miiunitoa
./install.sh                # CLI と拡張機能を所定の場所にシンボリックリンク
gnome-extensions enable miiunitoa@meeksi39
```

`install.sh` は拡張機能の GSettings スキーマ（自動切り替えのトグル・既定
レイアウト・サイクル用ショートカットで使用）もコンパイルします。スキーマを
変更した場合は `./install.sh` を再実行し、シェルを再読み込みしてください。

Wayland では、新しくインストールした拡張機能を GNOME Shell に読み込ませるため、
**一度ログアウトして再ログイン**する必要があります（X11 なら `Alt+F2` →
`r` で再読み込みできます）。

`./install.sh` は既定でシンボリックリンクを作成するため、リポジトリ内のファイルを
編集すればすぐに反映されます。その他のモード:

```sh
./install.sh --copy        # シンボリックリンクではなくファイルをコピー
./install.sh --uninstall   # リンク／コピーを削除（保存済みレイアウトは残す）
```

### インストール／アンインストールの動作

`install.sh` が操作するのは次の 3 か所だけです:

- `~/.local/bin/monitor-layout` — CLI（シンボリックリンク。`--copy` ならコピー）
- `~/.local/bin/ml` — CLI への短いエイリアス（シンボリックリンク）
- `~/.local/share/gnome-shell/extensions/miiunitoa@meeksi39/` — 拡張機能

既存の**実体**ファイル／ディレクトリの上にインストールする場合は、まず
`<パス>.bak.<タイムスタンプ>` へ退避するため、何も失われません。インストーラーは
何度実行しても安全です。

**アンインストールはこの 3 か所だけを削除します。** 次のものは決して削除しません:

- **保存済みレイアウト** `~/.config/monitor-layouts/` — 常に保持されます。
  そのため、アンインストールして再インストールしてもレイアウトは失われません。
- インストーラーが作成した `*.bak.*` バックアップ — これはインストール前の
  オリジナルなので、不要であれば手動で削除してください。

アンインストール後は、拡張機能も無効化してください:

```sh
gnome-extensions disable miiunitoa@meeksi39
```

## 使い方

### 現在の構成を保存する

**設定 → ディスプレイ**でモニターを好みの配置にしてから:

```sh
ml save work        # 現在のレイアウトを "work" として保存
ml save fps         # 別のレイアウトも保存
```

### レイアウトを切り替える

コマンドラインから:

```sh
ml list             # 保存済みレイアウトを概要付きで一覧表示
ml apply work       # "work" レイアウトに切り替え
ml current          # 現在のレイアウトを表示（保存される形式で）
ml rename fps game  # 保存済みレイアウトの名前を変更
ml delete fps       # 保存済みレイアウトを削除
ml active           # 現在の構成に一致する保存済みレイアウト名を表示（あれば）
ml match            # 接続中のモニターで使える保存済みレイアウトを表示
ml match --apply    # 最も適合するレイアウトを適用
```

または**トップバー**から: ディスプレイアイコンをクリックします。各レイアウトは
**Apply（適用）**・**Set as default（既定に設定）**・**Delete（削除）** を持つ
サブメニューに展開され、概要（モニター数と接続先）も表示されます。現在の構成に
一致するレイアウトにはチェックマークが、既定のレイアウトには ★ が付きます。
「Save current layout…」で現在の構成に名前を付けて保存でき、「Display Settings…」で
GNOME のディスプレイ設定パネルが開きます。メニューは開くたびに再構築されるため、
CLI で保存したレイアウトも拡張機能を再読み込みせずに表示されます。

（`ml` は `monitor-layout` の短いエイリアスです。どちらを使っても構いません。）

### キーボードショートカット

**`Super+P`** で次の保存済みレイアウト（名前順）に切り替わります。dconf で
変更できます:

```sh
dconf write /org/gnome/shell/extensions/miiunitoa/cycle-layouts "['<Super>F8']"
```

### 抜き差し時の自動切り替え

**Auto-switch on hotplug**（メニューで切り替え。既定で有効）が有効なときは、
モニターを抜き差しすると、その時点で接続されているモニターに適合する保存済み
レイアウトが自動で適用され、通知が表示されます。

レイアウトが**適合する**のは、そのレイアウトが使う接続先がすべて現在接続されて
いる場合です。そのため、ノートPCの画面を無効化した「ドック」レイアウトも、
ドック中はちゃんと適合します。複数が適合する場合は **既定（default）** に設定した
ものが優先され、なければ最も多くのモニターを使うものが選ばれます。同数のものが
複数あり既定もない場合は、何も適用されません（既定を設定して曖昧さを解消して
ください）。これは `ml match` と同じロジックです。

## 仕組み

- **保存（save）** では `org.gnome.Mutter.DisplayConfig` の `GetCurrentState` を
  呼び出し、各論理モニターの位置（`x`,`y`）・`scale`・`transform`（回転）・
  `primary` フラグ、および各物理モニターの `connector`（例: `DP-4`）と現在の
  `mode_id`（例: `1920x1080@200.000`）を記録します。
- **適用（apply）** では保存した JSON を読み込み、`ApplyMonitorsConfig` を
  `PERSISTENT`（2）メソッドで呼び出すため、変更は再起動後も保持されます。

### レイアウトファイルの形式

```json
{
  "logical_monitors": [
    {
      "x": 0, "y": 0,
      "scale": 1.0,
      "transform": 0,
      "primary": true,
      "monitors": [
        { "connector": "DP-4", "mode_id": "1920x1080@200.000" }
      ]
    }
  ]
}
```

`transform` の値: `0` 通常、`1` 90°、`2` 180°、`3` 270°、`4〜7` は反転
（flipped）の各バリエーション。

## トラブルシューティング

- **「Failed to apply … connectors/modes may not match」** — 保存したレイアウトが
  現在利用できない接続先や解像度を参照しています（モニター未接続、別ポート、
  非対応モードなど）。現在のハードウェア構成でレイアウトを保存し直してください。
- **拡張機能が表示されない** — 有効になっているか確認し
  （`gnome-extensions list --enabled`）、Wayland ではログアウト／再ログインした
  か確認してください。
- **`ml: command not found`** — `~/.local/bin` が `PATH` に入っていません。
- **メニューにレイアウトがない** — まだ保存していません。`ml save <name>` を
  実行してください。

## 開発

リポジトリが正本（source of truth）です。シンボリックリンクでインストールした
場合、`bin/monitor-layout` を編集して再実行するだけで反映されます。拡張機能を編集
した場合は GNOME Shell を再読み込みしてください（Wayland ではログアウト／
再ログイン）。拡張機能のログは次のコマンドで確認できます:

```sh
journalctl -f -o cat /usr/bin/gnome-shell
```
