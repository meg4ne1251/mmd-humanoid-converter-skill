# GEMINI.md — mmd-humanoid-converter-skill

## このプロジェクトは何か

MMD（MikuMikuDance）モデルを **Humanoid 形式モデルへ変換する作業を、手動ではなく AI アシスタント + Blender MCP で（半）自動化するスキル** を制作するプロジェクト。

これまで `docs-not-commit/` に書かれた手順を人間が手動で Blender 上で実行していた。その一連の作業を、Gemini が Blender MCP を通じて bpy コードを実行することで代行できるようにするのが目標。

## 配布方針（重要）

- このリポジトリは **Public リポジトリとして配布** する。
- 最終形は **AI スキルとして単一スキルリポジトリ** で配布する（リポジトリ＝1スキル）。**リポジトリ名は `mmd-humanoid-converter-skill`、スキル名（`SKILL.md` の `name:`）は `mmd-humanoid-converter`** とする（リポジトリ名にだけ `-skill` を付ける）。
- つまりルートに `SKILL.md` を置き、リポジトリをクローンすればそのままスキルとして使える構成を目指す。
- **Claude と Gemini の両方に対応** する。`CLAUDE.md`（Claude 向け）と `GEMINI.md`（Gemini 向け・このファイル）の両方を配置。

## Gemini でのスキル利用（開発者向け）

Gemini CLI でこのスキルを使う場合の導入方法：

```bash
# プロジェクトの .gemini/skills/ にクローン
mkdir -p .gemini/skills
git clone https://github.com/meg4ne1251/mmd-humanoid-converter-skill.git \
  .gemini/skills/mmd-humanoid-converter

# Blender MCP サーバーの設定（.gemini/settings.json に追記）
# {
#   "mcpServers": {
#     "blender": {
#       "command": "uvx",
#       "args": ["blender-mcp"]
#     }
#   }
# }
```

**開発時の構成**: このリポジトリを直接開発する場合は `.gemini/skills/mmd-humanoid-converter/` にルートの `SKILL.md` と `references/` へのシンボリックリンクが置かれている。こうすることで、ルートのファイルを編集するだけで Gemini スキルにも反映される。

## 絶対に守ること

- **`docs-not-commit/` は絶対にコミットしない。** 元手順記事・参考画像・動画が入っており、公開リポジトリに含めてはいけない。`.gitignore` で除外済み（綴り違い `docs-note-commit/` も予防的に除外）。新しい参考資料を置くときも必ずこのフォルダ配下に置くこと。
- 破壊的な Blender 操作（ボーン削除・ウェイト削除等）は、実行前にシーンを inspect し、ユーザー確認を取ってから行う（Blender MCP の方針に従う）。
- モデルは構造・命名がバラバラなので **「決め打ち」をしない**。必ずシーンの実状態を読んでから判断する。

## 変換フロー（元記事の要約 = スキルが実装すべき手順）

対象は MMDtools で読み込んだ PMX/PMD モデル。目標は Humanoid 規格のボーン構造（下記）にすること。

1. **MMDtools アドオン導入 / モデル読込** — `.pmx/.pmd` をインポート（前提条件。スキルではユーザーに依頼 or 確認）。
2. **余計なオブジェクト削除** — 当たり判定等の物理オブジェクトを削除し、メッシュとアーマチュアのみ残す。
3. **ボーンコンストレイント解除** — ポーズモードで色付き（コンストレイント付き）ボーンの constraint を全削除。
4. **ボーン構造の変換（最重要）**
   - 腰ボーンが下向き → 180度回転して上向きにし、親子構造を再構築。センター/グループ/センター先等の MMD 特有ボーンを削除。
   - 腕の上向き補助ボーン・ねじれ（捩り）ボーンを削除。**削除前に、それらに乗っているウェイトを本来の腕ボーンへ転送する**（複数ボーンに分割されたウェイトを1ボーンへ集約）。
   - IK/FK 制御ボーン（足首・手首周り）を削除。ウェイトが乗っている場合は転送 or 手動で再ペイントしてから削除。
5. **`_shadow` / `_dummy` ボーン削除** — 非表示コレクションを表示にしてから削除（通常ウェイトなし）。
6. **ボーン命名を Humanoid 規格へリネーム** — 下記の Humanoid 命名へ。リネームでウェイトが外れる稀なケースがあるので都度動作確認。
7. **ボーン表示整形＋連結** — MMD Tools のインポート直後は全ボーンが `use_connect = False` で、親子関係はあっても各ボーンの head が親の tail から浮き、バラバラに見える。OCTAHEDRAL 表示・tail 方向を整えた上で、**幾何判定で連結する**：各子ボーンの head が親の tail とほぼ一致（距離 ≈ 0）していれば連結、離れていれば連結しない。名前リストや分岐ロジックは使わない純粋な座標判定で、**一致していれば揺れもの（袖・スカート・髪・帯）も含めて全て連結する**（作者がそれらの head も親の tail 上に置いているため）。元から一致している head のみ連結するので `use_connect` は head を動かさない無操作＝変形は不変。親の tail を動かさないため、多分岐の親でも複数の子を同時に連結できる。head が親 tail から離れたボーン（四肢の起点・浮いた制御ボーン）は一致しないので自動的に未連結のまま残る。連結後はポーズテスト。実機検証（196ボーンのきりたん）では距離分布が「完全一致133本」と「1%以上」にきれいに二分し、閾値は鋭敏でないことを確認済み。
8. **マテリアルを Principled BSDF へ変換（任意）** — MMD トゥーンシェーダ（旧: Emission+Transparent+Mix / 新: `mmd_shader` ノードグループ）を Principled BSDF へ再配線。テクスチャ/UV ノードは再利用し、`nodes.clear()` は使わない。エクスポート時にテクスチャを失わないための処理。
9. **パーツ分離** — 顔/髪/体/服/装飾などでメッシュを別オブジェクトに分離（最後に実施）。
10. **シェイプキーのリネーム** — `あ い う え お` → `a i u e o`。
11. **任意の仕上げ** — 末端ボーン削除、三角面→四角面、服で隠れる素体メッシュの作成。
12. 完了後 FBX 出力 → MotionBuilder でキャラクタライズ。

### ウェイト転送について

元記事には自作 Blender アドオン（`BWT_*` クラス群: VERTEX_WEIGHT_MIX モディファイアで頂点グループ間ウェイトを転送、LR反転・転送元削除対応）が含まれる。スキルでは同等の処理を bpy で直接実行できるようにするのが望ましい。SET（上書き）/ ADD（加算）モードがあり、加算は1回のみ（複数回でグラデが崩れる）。

## 目標ボーン階層

変換のゴールとなる Humanoid 階層（`docs-not-commit/.../image 11.png` より）:

```
Bones
└─ Reference
   └─ Parent
      └─ Hips
         ├─ UpLeg_L → Leg_L → Foot_L → Toe_L
         ├─ UpLeg_R → Leg_R → Foot_R → Toe_R
         └─ Spine1 → Spine2 → Spine3
            ├─ Shoulder_L → UpArm_L → ForeArm_L → Hand_L
            ├─ Shoulder_R → UpArm_R → ForeArm_R → Hand_R
            └─ Neck → Head
```

腰（Hips）を起点に上方向へ伸びる。L/R はサフィックスで対になる。

## 注意・制約（元記事より）

- **MMD 変換に「絶対」は存在しない。** モデルごとに形式・構造が異なるため、手順は一例。全モデルの変換成功は保証されない。
- スキルは「全自動で完璧に変換」ではなく、「定型作業を代行し、判断が要る箇所はユーザーに確認・提示する」方針が現実的。

## Blender MCP メモ（Gemini 向け）

- Blender MCP のツールでシーン操作する。MCP サーバー名は `blender`（`.gemini/settings.json` で定義）。
- `execute_blender_code` は最終手段で、`get_objects_summary` / `get_object_detail_summary` / `search_api_docs` などの専用ツールを優先する。
- 操作前にモード（Object/Edit/Pose）・アクティブオブジェクト・選択状態を明示的に設定する。bmesh は edit mode で使い flush する。変更後は depsgraph を更新してから計算値を読む。
- **`execute_blender_code` 経由のコードは通常の UI コンテキストを持たない**ため、多くの `bpy.ops` オペレーターが context エラーで失敗する。データレベル API を優先し、オペレーターが必要な場合は VIEW_3D コンテキストオーバーライドを使う（詳細は `SKILL.md` の「Running operators through the Blender MCP」セクション参照）。

## リポジトリ構成

```
/ (リポジトリルート = スキル本体)
├─ SKILL.md           # スキル定義（変換フローのオーケストレーション）
├─ references/         # ステップ別の詳細（bpy コード＋落とし穴）
├─ CLAUDE.md           # Claude 向けプロジェクトメモ
├─ GEMINI.md           # Gemini 向けプロジェクトメモ（このファイル）
├─ README.md           # 公開用説明
├─ LICENSE             # MIT ライセンス
├─ .gitignore
├─ .gemini/            # Gemini CLI 設定（開発用）
│  ├─ settings.json    #   Blender MCP サーバー設定
│  └─ skills/          #   ルートへのシンボリックリンク（.gitignore 対象）
└─ docs-not-commit/    # 参考資料（コミットしない）
```
