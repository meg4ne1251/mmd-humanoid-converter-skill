# mmd-humanoid-converter

MMD（MikuMikuDance）の `.pmx` / `.pmd` モデルを、Blender 上できれいな **Humanoid リグ** に変換する **AI スキル**（Claude / Gemini 対応）です。AI アシスタントが **Blender MCP** を通じて Blender を操作し、変換作業を代行します。

MMD 特有のボーン（ねじれ／IK／センター／グループボーンなど）の削除、複数ボーンに分割されたウェイトを本来の手足ボーンへ集約する転送、下向きの MMD 腰ボーンを上向きの Humanoid `Hips` へ作り直す処理、Humanoid 命名規則へのリネーム、親ボーンの tail と一致する子ボーンを幾何判定で連結するボーン整形、MMD トゥーンマテリアルの Principled BSDF への変換、メッシュのパーツ分離、日本語の母音シェイプキーのリネーム、までを扱います。

> ⚠️ **MMD 変換に「絶対」は存在しません。** モデルごとに構造も命名もバラバラなため、このスキルは **半自動** です。定型作業は代行しますが、判断が必要な箇所（特にボーン・ウェイトの破壊的操作）は必ずユーザーに確認します。すべてのモデルを完璧にノータッチで変換できることは保証しません。

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
11. 仕上げと FBX 出力（→ MotionBuilder でキャラクタライズ）

各ステップの具体的な bpy コードと、実機検証で判明した落とし穴は `references/` 配下の個別ファイルにまとめてあります。

## 前提条件

このスキルを使うには、事前に次の環境が整っている必要があります。

- **Blender 4.x または 5.x** がインストールされていること（バージョンによりノードのソケット名などが異なりますが、スキルは両対応です）。
- Blender に **[MMD Tools](https://extensions.blender.org/add-ons/mmd-tools/)** アドオンが導入済みであること。
- 変換対象の MMD モデルが、MMD Tools 経由ですでに **Blender にインポート済み**であること（File → Import → MikuMikuDance Model）。**インポート自体はこのスキルの対象外**なので、シーンに何もない場合はまずユーザー側でインポートしてください。
- **[Blender MCP](https://github.com/ahujasid/blender-mcp)** がセットアップ済みであること（Blender アドオンの導入 + MCP サーバーの接続）。セットアップ手順はリポジトリの README を参照してください。
- **スキルに対応した AI クライアント**:
  - Claude: Claude Code / Cowork など（**Opus 推奨**。Sonnet でも動作しますが、複雑なステップで勘違いの可能性がやや高くなります）
  - Gemini: Gemini CLI（`.gemini/skills/` にスキルを配置）
- **変換前に .blend ファイルのバックアップを取ること。** このスキルはボーンの削除・ウェイト統合・ペアレント再構築など、元に戻せない変更を行います。スキル開始前に必ずファイルを別名で保存（File → Save Copy… またはファイルを複製）しておいてください。スキルはバックアップの確認が取れてから作業を開始します。

## 導入方法

このリポジトリ**そのもの**が 1 つのスキルです（単一スキルリポジトリ）。

### Claude の場合

スキルを読み込むディレクトリにクローンしてください。

```bash
git clone https://github.com/meg4ne1251/mmd-humanoid-converter-skill.git
```

フォルダを Claude にスキルとして認識させます（お使いのクライアントがスキルを読み込む場所に配置）。

さらに Blender MCP サーバーを登録します（Claude Code の場合）:

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

さらに `.gemini/settings.json` に Blender MCP サーバーの設定を追加します（未設定の場合）:

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

1. **Blender 側**: MMD Tools で `.pmx` / `.pmd` をインポートし、Blender MCP サーバーを起動して AI クライアントに接続します。
2. **AI 側**: 例えば「Blender に MMD モデルをインポートしたので、Humanoid リグに変換して」のように依頼します。
3. AI がシーンを調査したあと、最初に **2 つの実行モード** を提示します。
   - **A）ステップ実行モード（推奨）**: 各破壊的操作の前に、削除・変更内容とその理由を提示して確認を取ってから実行します。初めてのモデルや構造が複雑なモデルにはこちらを推奨します。
   - **B）一括実行モード**: 確認なしで全フェーズを連続実行します。ただし「想定外のボーンにウェイトが乗っている」「ボーン名が想定と大きく異なり自動マッピングできない」「アーマチュアが複数ある」などの場合は中断して報告します。

   どちらのモードでも、最初のシーン調査（Step 0）は必ず実行し、見つかった内容のサマリを提示してから作業に入ります。

変換は一気通貫で完璧に終わるものではなく、モデルによっては手作業の補正が必要になります。各削除バッチのあとはポーズテストでメッシュがリグに追従するか確認しながら進めるのが安全です。

## 注意事項

- **「決め打ち」をしないこと。** モデルごとに形式・命名・階層が違うため、ボーン名や構造を仮定してはいけません。必ずシーンの実状態を読んでから判断します。
- **変換後は必ずリグの変形を確認すること。** ポーズテストで破綻がないかチェックし、モデルによっては手動補正を見込んでください。
- **元 MMD モデルの配布規約・ライセンスを尊重すること。** 変換したアセットを利用する際は、元モデルの利用条件に従ってください。

## リポジトリ構成

```
.
├── SKILL.md          # スキル本体（変換フローのオーケストレーション）
├── references/       # ステップ別の詳細（bpy コード＋落とし穴）
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
│   ├── bone-naming.md
│   └── material-bsdf.md
├── CLAUDE.md         # Claude 向けプロジェクトメモ
├── GEMINI.md         # Gemini 向けプロジェクトメモ
├── LICENSE           # MIT ライセンス
└── README.md
```

## ライセンス・免責

このスキル自体（コードおよびドキュメント）は **MIT ライセンス**で提供します（リポジトリ同梱の `LICENSE` を参照）。現状のまま（as-is）で提供し、MMD モデルの変換結果はモデルによって異なります。変換後は必ずリグの変形を検証し、一部のモデルでは手作業の補正が必要になることを想定してください。

なお **MIT ライセンスはこのスキルに対するものであり、変換対象の MMD モデルには適用されません。** 変換したアセットを利用する際は、元 MMD モデルの配布規約・ライセンスを尊重してください。
