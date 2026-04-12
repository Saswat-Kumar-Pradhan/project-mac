import streamlit as st
import requests
import os
import time

st.set_page_config(page_title="MACADS", layout="wide")

if "token" not in st.session_state:
    st.session_state["token"] = None
    
API_URL = os.getenv("API_URL", "http://localhost:8000")

def handle_login(email, password):
    try:
        res = requests.post(f"{API_URL}/api/auth/login", data={"username": email, "password": password})
        if res.status_code == 200:
            st.session_state["token"] = res.json().get("access_token")
            st.rerun()
        else:
            st.error(res.json().get("detail", "Login failed"))
    except Exception as e:
        st.error(f"Cannot connect to the backend: {e}")

def handle_signup(email, password, confirm, role):
    if password != confirm:
        st.error("Passwords do not match!")
        return
    try:
        res = requests.post(f"{API_URL}/api/auth/register", json={"email": email, "password": password, "role": role})
        if res.status_code == 200:
            st.success("Account created! You can now log in.")
        else:
            st.error(res.json().get("detail", "Registration failed"))
    except Exception as e:
        st.error(f"Backend error: {e}")

def upload_zip(file, personas):
    headers = {"Authorization": f"Bearer {st.session_state['token']}"}
    files = {"file": (file.name, file, "application/zip")}
    data = {"personas": ",".join(personas)}
    res = requests.post(f"{API_URL}/api/projects/upload", headers=headers, data=data, files=files)
    if res.status_code == 200:
        st.success(f"Project created! ID: {res.json()['id']}")
    else:
        st.error(f"Upload failed: {res.json().get('detail', res.text)}")

def save_github(url, personas):
    headers = {"Authorization": f"Bearer {st.session_state['token']}"}
    res = requests.post(f"{API_URL}/api/projects/github", headers=headers, json={
        "github_url": url, 
        "personas": personas
    })
    if res.status_code == 200:
        st.success(f"Project created! ID: {res.json()['id']}")
    else:
        st.error(f"Failed: {res.json().get('detail', res.text)}")

def search_code(project_id, query):
    headers = {"Authorization": f"Bearer {st.session_state['token']}"}
    res = requests.post(f"{API_URL}/api/projects/{project_id}/search", headers=headers, json={"query": query})
    if res.status_code == 200:
        return res.json().get("results", [])
    else:
        st.error(f"Search error: {res.json().get('detail', res.text)}")
        return []

def generate_docs(project_id):
    headers = {"Authorization": f"Bearer {st.session_state['token']}"}
    res = requests.post(f"{API_URL}/api/projects/{project_id}/generate", headers=headers)
    if res.status_code == 200:
        st.success("Agents Dispatched!")
        time.sleep(1)
        st.rerun()
    else:
        st.error(f"Failed to generate: {res.json().get('detail', res.text)}")

def toggle_pause(project_id, action):
    headers = {"Authorization": f"Bearer {st.session_state['token']}"}
    res = requests.post(f"{API_URL}/api/projects/{project_id}/{action}", headers=headers)
    if res.status_code == 200:
        st.success(f"Project {action}d successfully!")
        st.rerun()
    else:
        st.error(f"Failed to {action} project.")

def fetch_logs(project_id):
    headers = {"Authorization": f"Bearer {st.session_state['token']}"}
    try:
        res = requests.get(f"{API_URL}/api/projects/{project_id}/logs", headers=headers)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

if st.session_state["token"] is None:
    st.title("Welcome to MACADS")
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    with tab1:
        email_in = st.text_input("Email", key="l_email")
        pwd_in = st.text_input("Password", type="password", key="l_pwd")
        if st.button("Login"): handle_login(email_in, pwd_in)
    with tab2:
        reg_email = st.text_input("Email", key="r_email")
        reg_pwd = st.text_input("Password", type="password", key="r_pwd")
        reg_confirm = st.text_input("Confirm", type="password", key="r_conf")
        reg_role = st.radio("Account Profile", ["user", "admin"], key="r_role")
        if st.button("Sign Up"): handle_signup(reg_email, reg_pwd, reg_confirm, reg_role)

else:
    @st.cache_data(show_spinner=False)
    def fetch_user_role(token):
        headers = {"Authorization": f"Bearer {token}"}
        try:
            res = requests.get(f"{API_URL}/api/users/me", headers=headers)
            if res.status_code == 200:
                return res.json().get("role", "user")
        except Exception:
            pass
        return "user"

    if st.session_state["token"]:
        st.session_state["role"] = fetch_user_role(st.session_state["token"])
    st.sidebar.success("Logged in")
    if st.sidebar.button("Logout"):
        st.session_state["token"] = None
        st.rerun()
        
    st.sidebar.divider()
    
    menu_items = []
    if st.session_state.get("role") == "admin":
        menu_items.extend(["Manage Users", "Manage Projects"])
    else:
        menu_items.extend(["Dashboard", "New Project"])
        
    page = st.sidebar.radio("Menu", menu_items)
    
    if page == "Dashboard":
        st.title("My Projects")
        headers = {"Authorization": f"Bearer {st.session_state['token']}"}
        res = requests.get(f"{API_URL}/api/projects/", headers=headers)
        if res.status_code == 200:
            projects = res.json()
            if not projects:
                st.info("No projects yet. Go to New Project!")
            
            for p in projects:
                with st.expander(f"{p['name']} (Status: {p['status']})"):
                    st.write(f"**ID**: {p['id']}, **Type**: {p['source_type']}, **Personas**: {', '.join(p['personas'])}")
                    
                    if p['status'] == "paused":
                        st.warning("Analysis Sequence Paused.")
                        if st.button("Resume Progress", key=f"res_{p['id']}", type="primary"):
                            toggle_pause(p['id'], "resume")
                    
                    elif p['status'] in ["created", "analyzing", "generating"]:
                        st.info(f"System State: {p['status'].title()}...")
                        
                        if p['status'] == "analyzing":
                            logs = fetch_logs(p['id'])
                            if logs:
                                latest_log = logs[-1]
                                st.progress(latest_log['percentage'] / 100)
                                
                                # Prominent Status Box for Current Activity
                                st.markdown(f"""
                                <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; border-left: 5px solid #007bff; margin-bottom: 20px;">
                                    <h4 style="margin: 0; color: #007bff;">🔍 Current Activity</h4>
                                    <p style="margin: 5px 0 0 0; font-family: monospace;">{latest_log['message']}</p>
                                </div>
                                """, unsafe_allow_value=True)
                                
                                with st.expander("Show Processing History Logs", expanded=False):
                                    for log in reversed(logs[:-1]): # Show history logs
                                        emoji = "ℹ️"
                                        if log['level'] == "warning": emoji = "⚠️"
                                        if log['level'] == "error": emoji = "❌"
                                        st.write(f"{emoji} {log['message']}")
                        
                        if st.button("Pause Process", key=f"pau_{p['id']}"):
                            toggle_pause(p['id'], "pause")
                            
                        # Refresh logic for active states
                        time.sleep(2)
                        st.rerun()
                        
                    elif p['status'] in ["completed", "documented"]:
                        st.success("Intelligence Processed!")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Repository Type:** {p.get('repository_type', 'Unknown')}")
                            st.write(f"**Frameworks:** {', '.join(p.get('frameworks', []) or [])}")
                        with col2:
                            st.write(f"**Entry Points:** {', '.join(p.get('entry_points', []) or [])}")
                            
                        if p['status'] == "completed":
                            if st.button("Generate AI Documentation", key=f"gen_{p['id']}", type="primary"):
                                generate_docs(p['id'])
                        
                        if p['status'] == "documented":
                            st.divider()
                            st.subheader("📚 Generated Documentation")

                            # Build tab list dynamically based on available docs
                            tab_labels = []
                            if p.get("sde_docs"): tab_labels.append("🛠 SDE Docs")
                            if p.get("pm_docs"):  tab_labels.append("📋 PM Docs")
                            if p.get("architecture_diagram"): tab_labels.append("🏗 Architecture")

                            if tab_labels:
                                tabs = st.tabs(tab_labels)
                                tab_idx = 0
                                if p.get("sde_docs"):
                                    with tabs[tab_idx]:
                                        st.markdown(p["sde_docs"])
                                        st.download_button("Download SDE Docs (.md)", data=p["sde_docs"], file_name=f"Project_{p['id']}_SDE.md", type="primary")
                                    tab_idx += 1
                                if p.get("pm_docs"):
                                    with tabs[tab_idx]:
                                        st.markdown(p["pm_docs"])
                                        st.download_button("Download PM Docs (.md)", data=p["pm_docs"], file_name=f"Project_{p['id']}_PM.md", type="primary")
                                    tab_idx += 1
                                if p.get("architecture_diagram"):
                                    with tabs[tab_idx]:
                                        st.code(p["architecture_diagram"], language="mermaid")
                            
                            st.divider()
                            st.write("**Global Actions**")
                            pdf_url = f"{API_URL}/api/projects/{p['id']}/export/pdf"
                            try:
                                pdf_res = requests.get(pdf_url, headers=headers)
                                if pdf_res.status_code == 200:
                                    st.download_button(
                                        label="Download Full PDF Report",
                                        data=pdf_res.content,
                                        file_name=f"MACADS_Report_{p['id']}.pdf",
                                        mime="application/pdf"
                                    )
                            except:
                                pass
                        st.divider()
                        st.subheader("Project Chat & Context Injection")
                        st.write("Ask questions or provide mid-analysis instructions (e.g. 'focus on auth').")
                        
                        if f"chat_history_{p['id']}" not in st.session_state:
                            st.session_state[f"chat_history_{p['id']}"] = []
                            
                        for msg in st.session_state[f"chat_history_{p['id']}"]:
                            with st.chat_message(msg["role"]):
                                st.write(msg["content"])
                                
                        query = st.chat_input(f"Chat with Project {p['id']}...", key=f"chat_input_{p['id']}")
                        if query:
                            st.session_state[f"chat_history_{p['id']}"].append({"role": "user", "content": query})
                            with st.chat_message("user"): st.write(query)
                            
                            chat_res = requests.post(
                                f"{API_URL}/api/projects/{p['id']}/chat",
                                headers=headers,
                                json={"query": query}
                            )
                            if chat_res.status_code == 200:
                                reply = chat_res.json()["reply"]
                                st.session_state[f"chat_history_{p['id']}"].append({"role": "assistant", "content": reply})
                                with st.chat_message("assistant"): st.write(reply)
                            else:
                                st.error("Q&A AI Engine Failed.")

                        st.divider()
                        st.subheader("🔍 Semantic Code Search")
                        s_query = st.text_input("Find logic or specific code patterns", key=f"sq_{p['id']}")
                        if st.button("Search Codebase", key=f"sb_{p['id']}") and s_query:
                            with st.spinner("Searching ChromaDB..."):
                                results = search_code(p['id'], s_query)
                                if results:
                                    for idx, r in enumerate(results):
                                        st.markdown(f"**File:** `{r['source']}`")
                                        st.code(r['content'], language="python")
                                else:
                                    st.warning("No results found.")
        else:
            st.error("Could not fetch projects.")
            
    elif page == "New Project":
        st.title("Create New Project")
        st.write("Configure your documentation agents for a new codebase.")
        
        mode = st.radio("Source Type", ["ZIP", "GitHub"])
        
        with st.form("project_creation_form", clear_on_submit=True):
            personas = []
            if st.checkbox("SDE (Software Engineer) Docs"): personas.append("SDE")
            if st.checkbox("PM (Product Manager) Docs"): personas.append("PM")
            
            file = None
            url = ""
            if mode == "ZIP":
                file = st.file_uploader("Upload Code (.zip)", type=["zip"])
            else:
                url = st.text_input("GitHub Repository URL", placeholder="https://github.com/user/repo")
            
            submitted = st.form_submit_button("Initiate Analysis", type="primary")
            
            if submitted:
                if not personas:
                    st.error("Select at least one persona (SDE or PM).")
                elif mode == "ZIP" and not file:
                    st.error("Please upload a .zip file.")
                elif mode == "GitHub" and not url:
                    st.error("Please enter a GitHub URL.")
                else:
                    if mode == "ZIP":
                        with st.status("Uploading and initializing agents...", expanded=True) as status:
                            upload_zip(file, personas)
                            status.update(label="Initialization Complete!", state="complete", expanded=False)
                    else:
                        with st.status("Connecting to GitHub and initializing agents...", expanded=True) as status:
                            save_github(url, personas)
                            status.update(label="Queueing Analysis...", state="complete", expanded=False)
                    st.toast("Project created successfully!", icon="🚀")
                
    elif page == "Manage Users":
        st.title("Manage Users")
        st.write("System Administrators User Repository")
        
        with st.expander("Register New User or Admin Account"):
            with st.form("admin_create_user"):
                n_email = st.text_input("User Email")
                n_pwd = st.text_input("User Password", type="password")
                n_role = st.selectbox("Role", ["user", "admin"])
                if st.form_submit_button("Create Account"):
                    c_res = requests.post(f"{API_URL}/api/auth/register", json={"email": n_email, "password": n_pwd, "role": n_role})
                    if c_res.status_code == 200:
                        st.success("Account created securely.")
                        st.rerun()
                    else: st.error("Failed to create account.")
        st.divider()
        
        headers = {"Authorization": f"Bearer {st.session_state['token']}"}
        res = requests.get(f"{API_URL}/api/admin/users", headers=headers)
        if res.status_code == 200:
            users = res.json()
            for u in users:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 2])
                    c1.write(f"**Email**: `{u['email']}`")
                    c2.write(f"**Role**: `{u['role']}`")
                    with c3:
                        if st.button("Delete User", key=f"del_user_{u['id']}", type="primary"):
                            d_res = requests.delete(f"{API_URL}/api/admin/users/{u['id']}", headers=headers)
                            if d_res.status_code == 200:
                                st.success("User deleted!")
                                st.rerun()
                            else:
                                st.error("Failed to delete user.")
        else:
            st.error("Cannot fetch users.")
            
    elif page == "Manage Projects":
        st.title("Manage Projects")
        st.write("System Administrators Global Projects Grid")
        
        headers = {"Authorization": f"Bearer {st.session_state['token']}"}
        res = requests.get(f"{API_URL}/api/admin/projects", headers=headers)
        if res.status_code == 200:
            projects = res.json()
            if not projects:
                st.info("No projects in the system.")
                
            active_count = sum(1 for p in projects if p["status"] in ["analyzing", "generating", "uploaded"])
            st.metric("Running/Pending Analyses", active_count)
            st.divider()
            
            for p in projects:
                with st.expander(f"{p['name']} (Owner ID: {p.get('user_id', 'Unknown')})"):
                    st.write(f"**ID**: {p['id']} | **Type**: {p['source_type']} | **Status**: {p['status']}")
                    if st.button("Delete Project", key=f"del_proj_{p['id']}", type="primary"):
                        d_res = requests.delete(f"{API_URL}/api/admin/projects/{p['id']}", headers=headers)
                        if d_res.status_code == 200:
                            st.success("Project deleted!")
                            st.rerun()
                        else:
                            st.error("Failed to delete project.")
        else:
            st.error("Cannot fetch projects.")
