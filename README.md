# mmd-humanoid-converter

MMD（MikuMikuDance）の `.pmx` / `.pmd` モデルや保存済み `.blend` を、Blenderできれいな **Humanoid リグ** に変換する **AI スキル**（Claude / Gemini / Codex 対応）です。通常は **Blender CLIのバックグラウンド実行**で処理し、GUIの起動・MCP接続は不要です。対話的な修正が必要な場合にはGUI/MCPを使えます。

MMD 特有のボーン（ねじれ／IK／センター／グループボーンなど）の削除、複数ボーンに分割されたウェイトを本来の手足ボーンへ集約する転送、下向きの MMD 腰ボーンを上向きの Humanoid `Hips` へ作り直す処理、Humanoid 命名規則へのリネーム、親ボーンの tail と一致する子ボーンを幾何判定で連結するボーン整形、MMD トゥーンマテリアルの Principled BSDF への変換、メッシュのパーツ分離、日本語の母音シェイプキーのリネーム、までを扱います。

> **MMD 変換に「絶対」は存在しません。** モデルごとに構造も命名も異なるため、実データを調査して変換計画を作ります。ステップ実行では変更前に確認し、一括実行では未知の構造・曖昧な対応・エラーで停止します。

## このスキルが行うこと

変換のゴールとなるリグ（Humanoid 規格）の階層:

```
Reference → Parent → Hips
  Hips ├─ UpLeg_L → Leg_L → Foot_L → Toe_L
       ├─ UpLeg_R → Leg_R → Foot_R → Toe_R
       └─ Spine1 → Spine2 → Spine3
              ├─ Shoulder_L → UpArm_L → ForeArm_L → Hand_L (→ 指)
              ├─ Shoulder_R → UpArm_R → ForeArm_R → Hand_R (→ 指)
              └─ Neck → Head
```

腰（Hips）を起点として、すべてのボーンが**上方向**へ伸びる構造です。対して生の MMD リグは、腰が**下向き**（センター／グループ／センター先など）で、腕のウェイトを複数本に分割する上向きの「ねじれ／捩り」補助ボーンや、手首・足首まわりに独立した IK/FK 制御ボーンを持ちます。変換とは、この MMD リグを上の構造へ作り変える作業です。

### 変換フローの概要

1. シーンの調査（オブジェクト・アーマチュア・ボーン・ウェイト・マテリアルの実状態を読む）
2. 不要オブジェクトの削除（当たり判定・物理オブジェクトなど。メッシュとアーマチュアのみ残す）
3. ボーンコンストレイントの解除
4. ボーン構造の再構築（**最重要**。腰／背骨の作り直し、ねじれ・IK ボーンの削除とウェイト転送）
5. `_shadow` / `_dummy` ボーンの削除
6. Humanoid 命名規則へのリネーム
7. ボーン表示・テールの整形と幾何連結（親の tail と一致する子ボーンを座標判定で連結。揺れもの含む）
8. マテリアルを Principled BSDF へ変換（任意）
9. メッシュのパーツ分離
10. シェイプキーのリネーム（`あ い う え お` → `a i u e o`）
11. マテリアル／テクスチャ名の整理（マテリアル名 == ベーステクスチャ名に統一。FBX 出力前の最後の編集ステップ）
12. 仕上げと FBX 出力（先端ボーン削除〔名前に「先」を含むボーン〕、→ MotionBuilder でキャラクタライズ）
13. テクスチャの PNG 出力（任意・会話終了時確認。blend ファイルと同階層の `tex/` フォルダへ `テクスチャ名.png` として保存し Blender 内パスを更新）

各ステップの具体的な bpy コードと、実機検証で判明した落とし穴は `references/` 配下の個別ファイルにまとめてあります。

## 前提条件

このスキルを使うには、事前に次の環境が整っている必要があります。

- **Blender** がインストールされていること。新しいCLIの合成モデル統合テストは **5.1.1** で実施しています。他バージョン・実モデルは個別検証が必要です。
- 起動用の **Python 3.10以降**。`bpy` はBlender内蔵のPythonを使います。
- PMX/PMD入力の場合は **[MMD Tools](https://extensions.blender.org/add-ons/mmd-tools/)** が導入済みであること。インポート済み `.blend` の通常編集には不要です。
- 保存済みの入力ファイル。GUI上の未保存シーンを使う場合は、先に入力用コピーを保存してください。
- **スキルに対応した AI クライアント**:
  - Claude: Claude Code / Cowork など（**Opus 推奨**。Sonnet でも動作しますが、複雑なステップで勘違いの可能性がやや高くなります）
  - Gemini: Gemini CLI（`.gemini/skills/` にスキルを配置）
  - Codex: このプロジェクトまたはインストールしたスキルを読み込み、CLIを実行します。
- CLIは入力を上書きせず、**新規の出力ディレクトリ**と工程ごとのチェックポイントへ保存します。GUI/MCPで直接編集するときは別途バックアップを取ってください。

## 導入方法

このリポジトリ**そのもの**が 1 つのスキルです（単一スキルリポジトリ）。

### Claude の場合

スキルを読み込むディレクトリにクローンしてください。例えば Claude Code の場合は `~/.claude/skills/` 配下です:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/meg4ne1251/mmd-humanoid-converter-skill.git \
  ~/.claude/skills/mmd-humanoid-converter
```

（Cowork など他のクライアントの場合は、お使いのクライアントがスキルを読み込む場所に配置してください。）

CLIだけを使う場合、MCPサーバー登録は不要です。GUIで対話操作もする場合は、任意でBlender MCPサーバーを登録します（Claude Code の場合）:

```bash
claude mcp add blender uvx blender-mcp
```

読み込まれると、Blender 上の MMD モデルを変換・整理・Humanoid 化するよう依頼したときにスキルが起動します。

### Gemini CLI の場合

プロジェクトの `.gemini/skills/` ディレクトリにクローンしてください。

```bash
mkdir -p .gemini/skills
git clone https://github.com/meg4ne1251/mmd-humanoid-converter-skill.git \
  .gemini/skills/mmd-humanoid-converter
```

GUI/MCPも使う場合だけ、任意で `.gemini/settings.json` に以下を追加します:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["blender-mcp"]
    }
  }
}
```

Gemini CLI を起動すると、`SKILL.md` が自動的に読み込まれ、MMD モデルの変換を依頼したときにスキルが起動します。

## 使い方

1. 入力 `.blend` または `.pmx` / `.pmd` のパスを指定し、AIにHumanoid変換を依頼します。BlenderのGUI起動は不要です。
2. AIは実行モードを選択／引き継ぎ、CLIでシーンを調査してサマリーとモデル固有の変換計画を作ります。
3. 実行モードは以下の2種類です。
   - **A）ステップ実行モード（推奨）**: 各破壊的操作の前に、削除・変更内容とその理由を提示して確認を取ってから実行します。初めてのモデルや構造が複雑なモデルにはこちらを推奨します。
   - **B）一括実行モード**: 確認なしで全フェーズを連続実行します。ただし「想定外のボーンにウェイトが乗っている」「ボーン名が想定と大きく異なり自動マッピングできない」「アーマチュアが複数ある」などの場合は中断して報告します。

   どちらのモードでも、最初のシーン調査（Step 0）は必ず実行し、見つかった内容のサマリを提示してから作業に入ります。

4. 計画のドライラン、適用、数値ポーズ検査と画像生成、FBX・必要ならPNG出力、保存後再読込検査までCLIで実行します。画像での見た目確認と、後段ツールでの互換性検証も区別して報告します。

### CLIの入口

スキルのルートで実行します。`--output-dir` には、まだ存在しないディレクトリを指定してください。

```sh
python3 scripts/mmd_cli.py inspect "model.blend" --output-dir "work/01-inspect"
```

`report.json` の実情報から `plan.json` を作った後、各コマンドの成功を確認して順に実行します。

```sh
python3 scripts/mmd_cli.py apply "model.blend" --plan "plan.json" --dry-run --output-dir "work/02-preview"
python3 scripts/mmd_cli.py apply "model.blend" --plan "plan.json" --output-dir "work/03-converted"
python3 scripts/mmd_cli.py export "work/03-converted/converted.blend" --textures --require-humanoid --output-dir "work/04-export"
```

`inspect / apply / verify / render / export` を用意しています。Blenderは `--blender`、`BLENDER_BIN`、PATH、macOS標準アプリ位置の順で検出するため、対話シェルのaliasは不要です。対応する計画・検証項目・制限は **[CLI手順](references/cli-workflow.md)** を参照してください。

変換計画はモデルごとに作ります。ボーン名やマテリアルの分類を固定した全自動変換ではありません。GUIは手動モデリングやウェイトペイント等が必要な場合に使います。

## 注意事項

- **「決め打ち」をしないこと。** モデルごとに形式・命名・階層が違うため、ボーン名や構造を仮定してはいけません。必ずシーンの実状態を読んでから判断します。
- **変換後は必ずリグの変形を確認すること。** ポーズテストで破綻がないかチェックし、モデルによっては手動補正を見込んでください。
- **元 MMD モデルの配布規約・ライセンスを尊重すること。** 変換したアセットを利用する際は、元モデルの利用条件に従ってください。

## リポジトリ構成

```
.
├── SKILL.md          # スキル本体（変換フローのオーケストレーション）
├── scripts/          # CLIランチャーとBlender側の処理
├── tests/            # 合成モデルによるCLI統合テスト
├── references/       # ステップ別の詳細（bpy コード＋落とし穴）
│   ├── cli-workflow.md
│   ├── 01-inspect.md
│   ├── 02-cleanup-objects.md
│   ├── 03-constraints.md
│   ├── 04-bone-structure.md
│   ├── 05-weight-transfer.md
│   ├── 06-verify-rig.md
│   ├── 07-shadow-dummy.md
│   ├── 08-rename.md
│   ├── 09-bone-display.md
│   ├── 10-separate-parts.md
│   ├── 11-shapekeys.md
│   ├── 12-finishing-export.md
│   ├── 13-material-texture-rename.md
│   ├── 14-texture-export.md
│   ├── bone-naming.md
│   └── material-bsdf.md
├── material-texture-namer/  # 同梱の単独サブスキル（下記参照）
│   ├── SKILL.md
│   ├── README.md
│   └── references/material-texture-namer.md
├── CLAUDE.md         # Claude 向けプロジェクトメモ
├── GEMINI.md         # Gemini 向けプロジェクトメモ
├── LICENSE           # MIT ライセンス
└── README.md
```

### 同梱スキルについて

このリポジトリにはメインの `mmd-humanoid-converter` スキル（ルートの `SKILL.md`）に加えて、`material-texture-namer/` に**単独でも使えるサブスキル**を同梱しています。これは変換フローの Step 11（マテリアル／テクスチャ名の整理）を、MMD 変換に限らず任意の Blender モデルへ単体で適用できるよう切り出したものです。詳細は `material-texture-namer/README.md` を参照してください。

## ライセンス・免責

このスキル自体（コードおよびドキュメント）は **MIT ライセンス**で提供します（リポジトリ同梱の `LICENSE` を参照）。現状のまま（as-is）で提供し、MMD モデルの変換結果はモデルによって異なります。変換後は必ずリグの変形を検証し、一部のモデルでは手作業の補正が必要になることを想定してください。

なお **MIT ライセンスはこのスキルに対するものであり、変換対象の MMD モデルには適用されません。** 変換したアセットを利用する際は、元 MMD モデルの配布規約・ライセンスを尊重してください。
