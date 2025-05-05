import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os 

st.set_page_config(page_title="FinApp", page_icon= "$$", layout = "wide")
#streamlit UI
category_file = "categories.json" #variable
if "categories" not in st.session_state:
    st.session_state.categories = {
        "Uncategorized": [],
    }
    
if os.path.exists(category_file): 
    with open("categories.json", "r") as f:
        st.session_state.categories = json.load(f)

def save_categories(): #function that lets us save categories 
    with open(category_file, "w") as f:
        json.dump(st.session_state.categories, f)

def categorize_transactions(df):
        df["Category"] = "Uncategorized"
        
        for category, keywords in st.session_state.categories.items():
            if category == "Uncategorized" or not keywords:
                continue 
            
            lowered_keywords = [keyword.lower().strip() for keyword in keywords]
            
            for idx, row in df.iterrows():
                details = row["Details"].lower().strip()
                if details in lowered_keywords:
                    df.at[idx, "Category"] = category 
                    
        return df
        
def load_transactions(file): #function that defines transactions
    try:
        df = pd.read_csv(file)  #loading in the file to be read
        df.columns = [col.strip() for col in df.columns] #remove white spaces for columns
        df["AmountCharged"] = df["AmountCharged"].str.replace (",", "").astype(float) #replacing , with " " and converting to float
        # Try to parse dates with flexible format detection and error handling
        try:
            # First attempt with dayfirst=True for most common format
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors='coerce')
            
            # Check for any NaT (Not a Time) values from parsing errors
            if df["Date"].isna().any():
                st.warning(f"Some dates couldn't be parsed. Rows with invalid dates will be highlighted.")
            
            # Create formatted date string column
            df["Date_formatted"] = df["Date"].dt.strftime("%m/%d/%Y")
            
            # For debugging - show problematic rows
            problem_rows = df[df["Date"].isna()]
            if not problem_rows.empty:
                st.error(f"Warning: {len(problem_rows)} rows have invalid dates.")
        except Exception as e:
            st.error(f"Error processing dates: {str(e)}")
            return None
        return categorize_transactions(df) #df = dataframe
    except Exception as e:
        st.error(f"error proccessing file: {str(e)}")
        return None #f string to wrap error variable
def add_keyword_to_category(category, keyword):
    keyword = keyword.strip()
    if keyword and keyword not in st.session_state.categories[category]:
        st.session_state.categories[category].append(keyword)
        save_categories()
        return True
    return False

def main(): #main function 
    st.title("Personal Finance dashboard")
    
    uploaded_file = st.file_uploader("Upload your transaction or bank statement CSV file", type=["csv"])
    #file is stored here in the uploaded file variable
    if uploaded_file is not None:
        df = load_transactions(uploaded_file)
        
        if df is not None:
            debits_df = df[df["Debit/Credit"]== "Debit"].copy()
            credits_df = df[df["Debit/Credit"]== "Credit"].copy()
            #seperates two tabs by credit payments or debit expenses
            
            st.session_state.debits_df = debits_df.copy()
            
            tab1, tab2 = st.tabs(["Expenses (Debits)", "Payments (Credits)"])
            
            with tab1:
                new_category = st.text_input("New category Name")
                add_button = st.button("Add Category")
                
                if add_button and new_category:
                    if new_category not in st.session_state.categories:
                        st.session_state.categories[new_category] = []
                        save_categories()
                        st.rerun()
                        
                st.subheader("Your Expenses")
                edited_df = st.data_editor(
                     st.session_state.debits_df[["Date", "Details", "AmountCharged", "Category"]],
                     column_config={
                         "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                        "AmountCharged": st.column_config.NumberColumn("AmountCharged", format="%.2f USD"),
                        "Category": st.column_config.SelectboxColumn(
                            "Category",
                             options=list(st.session_state.categories.keys())
                        )
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="category_editor"
                )
                
                save_button = st.button("Apply Changes", type= "primary")
                if save_button:
                    for idx, row in edited_df.iterrows():
                        new_category = row["Category"]
                        if new_category == st.session_state.debits_df.at[idx, "Category"]:
                            continue
        
                        details = row["Details"]  # or "Details" if you've renamed the column
                        st.session_state.debits_df.at[idx, "Category"] = new_category
                        add_keyword_to_category(new_category, details)

                st.subheader('Expense Summary')
                category_totals = st.session_state.debits_df.groupby("Category")["AmountCharged"].sum().reset_index()
                category_totals = category_totals.sort_values("AmountCharged", ascending=False)
                    
                st.dataframe(
                    category_totals,
                    column_config={
                        "AmountCharged": st.column_config.NumberColumn("AmountCharged", format="%.2f USD")
                    },
                    use_container_width=True,
                    hide_index=True
                )
                fig = px.pie(
                    category_totals,
                    values="AmountCharged",
                    names="Category", 
                    title="Expenses by Category"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                st.subheader("Payment Summary")
                total_payments = credits_df["AmountCharged"].sum()
                st.metric("Total payments", f"{total_payments:,.2f} USD")
                st.write(credits_df)
                
main()