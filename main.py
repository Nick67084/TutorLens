"""TutorLens home page. Start the app with:  python -m streamlit run main.py"""
import streamlit as st

from core import config, llm_client, ui

st.set_page_config(page_title="TutorLens", page_icon="🎓", layout="wide")
ui.init()
ui.sidebar_student()

st.title("🎓 TutorLens")
st.subheader("An AI teacher that explains, quizzes and grades from your PDFs")

ok, message = llm_client.check_ollama()
if ok:
    st.success(message)
else:
    st.error(message)

st.markdown(
    """
**How to use it**

1. **Your name:** type it in the sidebar so your marks are saved.
2. **Upload:** add a text-based course PDF. The first time, the embedding model is downloaded.
3. **Learn:** ask questions about the PDF, or let the teacher explain a section step by step.
4. **Quiz:** generate questions, answer them and get AI marks with feedback.
5. **Marks:** see your scores for every quiz.

Every answer shows the PDF page it came from. If the answer is not in the PDF,
TutorLens says so instead of guessing.
"""
)
st.caption(f"Language model: {config.OLLAMA_MODEL or 'not set'} · Embedding model: {config.EMBEDDING_MODEL}")