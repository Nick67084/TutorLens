"""Learn page: the AI teacher explains the PDF and answers questions with page citations."""
import streamlit as st

from core import llm_client, teacher, ui, vector_store

st.set_page_config(page_title="Learn · TutorLens", page_icon="📖", layout="wide")
ui.init()
ui.sidebar_student()
doc = ui.sidebar_document()

st.title("📖 Learn")

if doc is None:
    st.info("No PDF yet. Go to the **Upload** page first.")
    st.stop()

ok, message = llm_client.check_ollama()
if not ok:
    st.error(message)
    st.stop()

mode = st.sidebar.radio("Mode", ["Ask a question", "Explain a section"])


def stream_answer(messages: list[dict]) -> str:
    """Show the answer while it is being written, and return the final text."""
    placeholder = st.empty()
    text = ""
    for piece in llm_client.stream_chat(messages):
        text += piece
        placeholder.markdown(text + "▌")
    final = teacher.clean_answer(text)
    placeholder.markdown(final)
    return final


if mode == "Ask a question":
    st.caption(f"Ask anything about “{doc['title']}”. Answers come only from this PDF.")
    chats = st.session_state.setdefault("chats", {})
    history = chats.setdefault(doc["id"], [])

    for item in history:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
            if item.get("sources"):
                st.caption(ui.format_sources(item["sources"]))

    question = st.chat_input("Ask about your PDF...")
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            try:
                sources = teacher.retrieve(doc["id"], question, history)
                if not sources:
                    answer = teacher.NOT_FOUND_MESSAGE
                    st.markdown(answer)
                else:
                    answer = stream_answer(teacher.build_answer_messages(question, sources, history))
                    if answer == teacher.NOT_FOUND_MESSAGE:
                        sources = []
                    else:
                        st.caption(ui.format_sources(sources))
                        with st.expander("Show the PDF text used for this answer"):
                            for s in sources:
                                st.markdown(f"**p.{s.page} · {s.section}**")
                                st.write(s.text)
            except Exception as error:
                st.error(f"Something went wrong: {error}")
                st.stop()
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer, "sources": sources})

else:
    sections = vector_store.get_sections(doc["id"])
    section = st.selectbox("Choose a section to learn", sections)
    if st.button("Explain this section", type="primary"):
        with st.chat_message("assistant"):
            try:
                sources = teacher.section_sources(doc["id"], section)
                stream_answer(teacher.build_section_messages(section, sources))
                st.caption(ui.format_sources(sources))
            except Exception as error:
                st.error(f"Something went wrong: {error}")