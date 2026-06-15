"""
PyMOL Streamlit App (Cloud Deploy Version)
"""
import os
import shutil
import tempfile
import streamlit as st
import glob
import traceback

# クラウド環境ではGUIが使えないため、ヘッドレスモード用の設定
os.environ['TCL_LIBRARY'] = '/usr/share/tcltk/tcl8.6'
os.environ['TK_LIBRARY'] = '/usr/share/tcltk/tk8.6'

try:
    import pymol2
    from pymol import util
    PYMOL_AVAILABLE = True
    error_detail = ""
except Exception as e:
    PYMOL_AVAILABLE = False
    error_detail = traceback.format_exc()

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# HEIC形式に対応するためのライブラリ
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

# --- ページ設定 ---
st.set_page_config(page_title="PyMOL Viewer Online", page_icon="🧬", layout="wide")
st.title("PyMOL Viewer Online")
st.write("ChemDraw等から出力したSDFファイルをアップロードして、3D構造や自転GIFを生成します。")

# ここが変更点！エラーの詳細を画面に表示させます
if not PYMOL_AVAILABLE:
    st.error("PyMOLの読み込みに失敗しました。以下の詳細なエラー文を教えてください！")
    st.code(error_detail)
    st.stop()

# --- セッション状態の初期化 ---
keys = ["t3_img", "t3_caption", "t3_angles", "t3_gif", "current_style"]
for key in keys:
    if key not in st.session_state:
        st.session_state[key] = None
if st.session_state.current_style is None:
    st.session_state.current_style = "スティック表示 (sticks)"

# --- ユーティリティ関数 ---
def _capture_png(c, width: int = 1200, height: int = 900, ray: int = 1) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = tmp.name
    try:
        c.png(path, width=width, height=height, dpi=150, ray=ray)
        with open(path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)

def _capture_four_angles(c) -> list:
    images = []
    for _ in range(4):
        images.append(_capture_png(c, width=800, height=600, ray=1))
        c.turn("y", 90)
    return images

def _capture_rotation_gif(c, focus_selection: str, n_frames: int = 36, width: int = 600, height: int = 450) -> bytes | None:
    if not PIL_AVAILABLE: return None
    c.center(focus_selection)
    c.zoom(focus_selection, buffer=1.0)
    c.refresh()

    tmp_dir = tempfile.mkdtemp()
    try:
        pil_frames = []
        angle_step = 360.0 / n_frames
        for _ in range(n_frames):
            with tempfile.NamedTemporaryFile(suffix=".png", dir=tmp_dir, delete=False) as tmp:
                frame_path = tmp.name
            c.png(frame_path, width=width, height=height, dpi=72, ray=0)
            pil_frames.append(Image.open(frame_path).convert("RGB"))
            c.turn("y", angle_step)

        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
            gif_path = tmp.name
        try:
            pil_frames[0].save(
                gif_path, save_all=True, append_images=pil_frames[1:],
                loop=0, duration=80, optimize=False,
            )
            with open(gif_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(gif_path): os.unlink(gif_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# =======================================================
# 化合物単体の3D可視化 (クラウド対応版)
# =======================================================
st.header("化合物ファイルの3D可視化")

col_t3_1, col_t3_2 = st.columns(2)
with col_t3_1:
    uploaded_single = st.file_uploader("化合物ファイル (.sdf, .mol) を選択:", type=["sdf", "mol"], key="tab3_up")
with col_t3_2:
    style_tab3 = st.selectbox("化合物の表示スタイル:", ["スティック表示 (sticks)", "空間充填モデル (spheres)"], key="style_tab3")

if st.button("単体画像を生成", type="primary", key="tab3_btn"):
    if uploaded_single:
        if style_tab3 != st.session_state.current_style:
            st.session_state.current_style = style_tab3
            for key in ["t3_img", "t3_angles", "t3_gif"]:
                st.session_state[key] = None

        with tempfile.NamedTemporaryFile(suffix=".sdf", delete=False) as tmp_sdf:
            tmp_single_path = tmp_sdf.name
            tmp_sdf.write(uploaded_single.getvalue())

        try:
            with st.spinner("PyMOLでレンダリング中..."), pymol2.PyMOL() as p:
                c = p.cmd
                c.load(tmp_single_path, "single_ligand")
                c.bg_color("white")
                
                c.set("display_mode", 1) 
                
                lig_style = "spheres" if "空間充填" in style_tab3 else "sticks"
                c.show_as(lig_style, "single_ligand")
                c.color("brightorange", "single_ligand")
                util.cnc("single_ligand", _self=c)
                
                c.set("ray_shadows", 0)
                c.set("antialias", 2)
                c.center("single_ligand")
                c.zoom("single_ligand", buffer=1.5)
                c.refresh()

                st.session_state.t3_img = _capture_png(c, 1200, 900, ray=1)
                
                with st.spinner("4方向ビュー生成中..."):
                    c.center("single_ligand"); c.zoom("single_ligand", buffer=1.5)
                    st.session_state.t3_angles = _capture_four_angles(c)
                    
                with st.spinner("GIF生成中..."):
                    st.session_state.t3_gif = _capture_rotation_gif(c, "single_ligand")

        except Exception as e:
            st.error(f"レンダリング中にエラーが発生しました: {e}")
        finally:
            if os.path.exists(tmp_single_path):
                os.unlink(tmp_single_path)
    else:
        st.warning("ファイルを選択してください。")

# --- 結果表示 ---
if st.session_state.t3_img:
    st.success("単体画像の生成完了！")
    st.image(st.session_state.t3_img, use_container_width=True)
    st.download_button("📥 ダウンロード", data=st.session_state.t3_img, file_name="ligand.png", mime="image/png", key="t3_dl1")
    
    if st.session_state.t3_angles:
        cols = st.columns(4)
        labels = ["Front", "Right", "Back", "Left"]
        for col, img, lbl in zip(cols, st.session_state.t3_angles, labels):
            with col:
                st.image(img, caption=lbl, use_container_width=True)
                st.download_button(f"📥 {lbl}", data=img, file_name=f"ligand_{lbl}.png", mime="image/png", key=f"t3_dl_{lbl}")
                
    if st.session_state.t3_gif:
        st.image(st.session_state.t3_gif, use_container_width=True)
        st.download_button("📥 GIFダウンロード", data=st.session_state.t3_gif, file_name="ligand.gif", mime="image/gif", key="t3_gif_dl")
