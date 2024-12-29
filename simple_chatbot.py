import sqlite3
from openai import OpenAI
import streamlit as st
import os
from ulid import ULID
import time
from sqlalchemy import text

db_path = 'chat.db'

def create_db():
    conn = st.connection('chat_db', type='sql')

    with conn.session as s:
        s.execute(text('create table if not exists chats (chat_id text primary key, title text, updated_at integer)'))
        s.execute(text('create index if not exists idx_chats_updated_at on chats(updated_at)'))
        s.execute(text('create table if not exists messages (chat_id text, message_no integer, role text, content text, model text, primary key (chat_id, message_no))'))
        s.commit()

create_db()

def save_chat(chat_id, title, messages):
    conn = st.connection('chat_db', type='sql')

    with conn.session as s:
        s.execute(
                text('delete from chats where chat_id = :chat_id'), 
                params={'chat_id': chat_id}
            )
        s.execute(
            text('insert into chats values (:chat_id, :title, :updated_at)'),
            params={'chat_id': chat_id, 'title': title, 'updated_at': (int)(time.time())}
        )

        s.execute(
            text('delete from messages where chat_id = :chat_id'),
            params={'chat_id': chat_id}
        )
        for i, message in enumerate(messages):
            s.execute(
                text('insert into messages values (:chat_id, :message_no, :role, :content, :model)'),
                params={
                    'chat_id': chat_id,
                    'message_no': i,
                    'role': message['role'],
                    'content': message['content'],
                    'model': message['model']
                }
            )
        
        s.commit()

def load_chat(chat_id):
    st.session_state.chat_id = chat_id
    conn = st.connection('chat_db', type='sql')

    df = conn.query(
        'select role, content, model from messages where chat_id = :chat_id order by message_no',
        params={'chat_id': chat_id}
    )

    st.session_state.messages = [{
        'role': message['role'],
        'content': message['content'],
        'model': message['model']} for  i, message in df.iterrows()]
    
    df2 = conn.query(
        'select title from chats where chat_id = :chat_id',
        params={'chat_id': chat_id}
    )

    st.session_state.title = df2.loc[0, 'title']

def set_title():
    if st.session_state.title == 'New Chat':
        st.session_state.title = generate_title(st.session_state.chat_input)

def chat_completions(model, messages):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    r = client.chat.completions.create(
        model=model,
        messages=[{'role': m['role'], 'content': m['content']} for m in messages],
    )
    return r.choices[0].message.content

def generate_title(content):
    messages=[{
        'role': 'user',
        'content':  '次の質問文を20文字で要約して。\r\n```\r\n' + content + '\r\n```'
    }]
    return chat_completions('gpt-3.5-turbo', messages)

def list_past_chats(page_no):
    conn = st.connection('chat_db', type='sql')

    df = conn.query(
        'select chat_id, title from chats order by updated_at limit 0, 10'
    )

    list_html = ['<li><a href="/?chat_id=' + chat['chat_id'] + '">' + chat['title'] + '</a></li>' for i, chat in df.iterrows()]
    st.sidebar.html('<a href="/">New Chat"</a><ul>' + ''.join(list_html) + '</ul>') 

list_past_chats(0)

if 'messages' not in st.session_state.keys():
    if 'chat_id' not in st.query_params:
        st.session_state.title = 'New Chat'
        st.session_state.messages = []
        st.session_state.chat_id = str(ULID())
    else:
        load_chat(st.query_params.chat_id)

model = st.selectbox(
    'モデル',
    ('gpt-3.5-turbo', 'gpt-4o')
)
st.title(st.session_state.title)

if prompt := st.chat_input(key = 'chat_input', on_submit=set_title):
    st.session_state.messages.append({'role': 'user', 'content': prompt, 'model': model})

for message in st.session_state.messages:
    with st.chat_message(message['role']):
        st.write(message['content'])

# If last message is not from assistant, we need to generate a new response
if len(st.session_state.messages) > 0 and st.session_state.messages[-1]['role'] != 'assistant':
    # Call LLM
    with st.chat_message('assistant'):
        with st.spinner('Thinking...'):
            response = chat_completions(model, st.session_state.messages)
            st.write(response)
            message = {'role': 'assistant', 'content': response, 'model': model}
            st.session_state.messages.append(message)
    
    save_chat(
        st.session_state.chat_id,
        st.session_state.title,
        st.session_state.messages,
    )
