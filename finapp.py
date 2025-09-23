import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
import io
import base64
from io import BytesIO
import PyPDF2
import tabula


# Import necessary libraries for Excel and PDF
# For Excel
import openpyxl
# For PDF - using PyPDF2 which is a common PDF library
try:
    import PyPDF2
    import tabula
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    
st.set_page_config(page_title="FinApp", page_icon= "$$", layout = "wide")

# Session state setup
category_file = "categories.json" 
if "categories" not in st.session_state:
    st.session_state.categories = {
        "Uncategorized": [],
    }
    
if os.path.exists(category_file): 
    with open("categories.json", "r") as f:
        st.session_state.categories = json.load(f)

def save_categories():
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

def clean_dates(df):
    """Fix problematic dates in the dataframe"""
    # Make a copy of the original Date column before processing
    df["Original_Date"] = df["Date"].copy()
    
    # Function to fix individual date entries
    def fix_date(date_str):
        try:
            # Try to parse as is
            return pd.to_datetime(date_str, errors='coerce')
        except:
            return pd.NaT
    
    # Apply the fix and handle specific edge cases
    df["Date"] = df["Date"].apply(fix_date)
    
    # Handle specific known issues
    if df["Original_Date"].dtype == 'object':  # Only process if string type
        # Handle 31/11 issue
        mask_nov31 = df["Original_Date"].str.contains("31/11", na=False)
        if mask_nov31.any():
            fixed_dates = df.loc[mask_nov31, "Original_Date"].str.replace("31/11", "30/11")
            df.loc[mask_nov31, "Date"] = pd.to_datetime(fixed_dates, dayfirst=True, errors='coerce')
        
        # Handle unusual month values
        mask_month_13plus = df["Original_Date"].str.contains(r"\d+/(?:1[3-9]|2[0-9]|3[0-9])/", na=False)
        if mask_month_13plus.any():
            fixed_dates = df.loc[mask_month_13plus, "Original_Date"].str.replace(
                r"(\d+)/(1[3-9]|2[0-9]|3[0-9])/", r"\1/12/", regex=True)
            df.loc[mask_month_13plus, "Date"] = pd.to_datetime(fixed_dates, dayfirst=True, errors='coerce')
    
    # Create formatted date string
    df["Date_formatted"] = df["Date"].dt.strftime("%m/%d/%Y")
    
    # Drop the temporary column
    df.drop("Original_Date", axis=1, inplace=True)
    
    # Report how many dates were fixed or are still problematic
    problem_count = df["Date"].isna().sum()
    return df, problem_count

def process_excel_file(file):
    """Process Excel files (xls, xlsx)"""
    try:
        # Read the Excel file into a pandas DataFrame
        df = pd.read_excel(file)
        
        # Basic validation - check required columns
        required_columns = ["Date", "Details", "AmountCharged", "Debit/Credit"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            # Try to map common column names to our expected format
            column_mapping = {
                # Date alternatives
                "Transaction Date": "Date",
                "TransactionDate": "Date",
                "Date of Transaction": "Date",
                "Tx Date": "Date",
                
                # Details alternatives
                "Description": "Details",
                "Merchant": "Details",
                "Transaction": "Details",
                "Payee": "Details",
                
                # Amount alternatives
                "Amount": "AmountCharged",
                "Value": "AmountCharged",
                "Transaction Amount": "AmountCharged",
                
                # Credit/Debit alternatives
                "Type": "Debit/Credit",
                "Transaction Type": "Debit/Credit"
            }
            
            # Apply the mappings
            df = df.rename(columns={v: k for k, v in column_mapping.items() 
                                   if v in df.columns and k in missing_columns})
            
            # Check again after mapping
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                # Still missing columns
                st.error(f"Excel file is missing required columns: {', '.join(missing_columns)}")
                st.info("Your Excel file should have columns: Date, Details, AmountCharged, Debit/Credit")
                return None
        
        # Process the data similarly to CSV
        df.columns = [col.strip() for col in df.columns]
        
        # Handle AmountCharged formatting
        if df["AmountCharged"].dtype == 'object':
            df["AmountCharged"] = df["AmountCharged"].astype(str).str.replace(",", "").replace("$", "", regex=True)
        df["AmountCharged"] = pd.to_numeric(df["AmountCharged"], errors='coerce')
        
        # Clean dates
        df, problem_count = clean_dates(df)
        if problem_count > 0:
            st.warning(f"{problem_count} dates couldn't be fixed and were set to NaT. These rows will be excluded from analysis.")
            df = df.dropna(subset=["Date"])
        
        return categorize_transactions(df)
        
    except Exception as e:
        st.error(f"Error processing Excel file: {str(e)}")
        return None

def extract_text_from_pdf(file):
    """Extract text content from a PDF file"""
    try:
        # Create a PDF reader object
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        
        # Extract text from each page
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text += page.extract_text()
            
        return text
    except Exception as e:
        st.error(f"Failed to extract text from PDF: {str(e)}")
        return None

def try_extract_tables_from_pdf(file_path):
    """Try to extract tables from PDF using tabula"""
    try:
        # Save the file temporarily
        with open(file_path, "wb") as f:
            f.write(file_path.getvalue())
            
        # Use tabula to extract tables
        tables = tabula.read_pdf(file_path, pages='all', multiple_tables=True)
        
        if not tables:
            return None
            
        # Combine all tables
        df = pd.concat(tables, ignore_index=True)
        return df
    except Exception as e:
        st.warning(f"Could not extract tables from PDF: {str(e)}")
        return None

def process_pdf_file(file):
    """Process PDF files and try to extract transaction data"""
    if not PDF_SUPPORT:
        st.error("PDF processing is not available. Please install PyPDF2 and tabula-py libraries.")
        st.info("Run: pip install PyPDF2 tabula-py")
        return None
        
    try:
        # First try to extract tables using tabula
        tables_df = try_extract_tables_from_pdf(file)
        
        if tables_df is not None and not tables_df.empty:
            # We got some tables, try to identify the transaction table
            st.success("Successfully extracted tables from PDF!")
            
            # Show the extracted tables and let user choose
            st.write("Preview of extracted data:")
            st.dataframe(tables_df.head())
            
            # Let user map columns if needed
            st.info("Please map the extracted columns to the required format.")
            
            # Get column names from the extracted table
            columns = tables_df.columns.tolist()
            
            # Create mapping UI
            col1, col2 = st.columns(2)
            with col1:
                date_col = st.selectbox("Which column contains Date?", 
                                       options=columns,
                                       key="date_col")
                                       
                details_col = st.selectbox("Which column contains Transaction Details?", 
                                         options=columns,
                                         key="details_col")
            
            with col2:
                amount_col = st.selectbox("Which column contains Amount?", 
                                        options=columns,
                                        key="amount_col")
                                        
                type_col = st.selectbox("Which column indicates Debit/Credit?", 
                                      options=columns + ["Not available - all debits", "Not available - all credits"],
                                      key="type_col")
            
            # Process button
            if st.button("Process PDF Data"):
                # Create a new DataFrame with the required structure
                df = pd.DataFrame()
                df["Date"] = tables_df[date_col]
                df["Details"] = tables_df[details_col]
                df["AmountCharged"] = tables_df[amount_col]
                
                # Handle the Debit/Credit column
                if type_col == "Not available - all debits":
                    df["Debit/Credit"] = "Debit"
                elif type_col == "Not available - all credits":
                    df["Debit/Credit"] = "Credit"
                else:
                    df["Debit/Credit"] = tables_df[type_col]
                
                # Set a default Status
                df["Status"] = "SETTLED"
                
                # Continue with processing like other file types
                df, problem_count = clean_dates(df)
                
                # Process amount charged
                if df["AmountCharged"].dtype == 'object':
                    df["AmountCharged"] = df["AmountCharged"].astype(str).str.replace(",", "").replace("$", "", regex=True)
                df["AmountCharged"] = pd.to_numeric(df["AmountCharged"], errors='coerce')
                
                return categorize_transactions(df)
            
            return None
        else:
            # If table extraction fails, extract text and inform user
            pdf_text = extract_text_from_pdf(file)
            
            if pdf_text:
                st.warning("Could not automatically extract structured data from this PDF.")
                st.info("PDF contains text but not in a easily recognizable table format.")
                st.text_area("Extracted Text (first 1000 characters):", pdf_text[:1000], height=200)
                st.info("You might need to manually extract data from this PDF or get a CSV/Excel version.")
            else:
                st.error("Could not extract any text from this PDF. It might be scanned or image-based.")
                
            return None
            
    except Exception as e:
        st.error(f"Error processing PDF file: {str(e)}")
        return None

def load_transactions(file, file_type): 
    """Process different file types based on extension"""
    try:
        if file_type == "csv":
            # Process CSV file
            df = pd.read_csv(file)
            df.columns = [col.strip() for col in df.columns]
            df["AmountCharged"] = df["AmountCharged"].str.replace(",", "").astype(float)
            
            # Clean dates
            df, problem_count = clean_dates(df)
            if problem_count > 0:
                st.warning(f"{problem_count} dates couldn't be fixed and were set to NaT. These rows will be excluded from analysis.")
                df = df.dropna(subset=["Date"])
            
            return categorize_transactions(df)
            
        elif file_type in ["xlsx", "xls"]:
            # Process Excel file
            return process_excel_file(file)
            
        elif file_type == "pdf":
            # Process PDF file
            return process_pdf_file(file)
            
        else:
            st.error(f"Unsupported file type: {file_type}")
            return None
            
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None

def add_keyword_to_category(category, keyword):
    keyword = keyword.strip()
    if keyword and keyword not in st.session_state.categories[category]:
        st.session_state.categories[category].append(keyword)
        save_categories()
        return True
    return False

def main(): 
    st.title("Personal Finance Dashboard")
    
    # File uploader with multiple file types
    uploaded_file = st.file_uploader(
        "Upload your transaction or bank statement file", 
        type=["csv", "xlsx", "xls", "pdf"]
    )
    
    if uploaded_file is not None:
        # Determine file type from extension
        file_type = uploaded_file.name.split(".")[-1].lower()
        
        # Show file type info
        st.info(f"Processing {file_type.upper()} file: {uploaded_file.name}")
        
        # Process the file based on its type
        df = load_transactions(uploaded_file, file_type)
        
        if df is not None:
            debits_df = df[df["Debit/Credit"]== "Debit"].copy()
            credits_df = df[df["Debit/Credit"]== "Credit"].copy()
            
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
                         "Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY"),
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
        
                        details = row["Details"]
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
                
    # Add instructions at the bottom
    with st.expander("Help & Instructions"):
        st.markdown("""
        ### Supported File Types
        - **CSV**: Standard comma-separated values files with transaction data
        - **Excel**: Both .xlsx and .xls formats with transaction data
        - **PDF**: The app will attempt to extract tables from PDF statements
        
        ### Required Columns
        Your file should have these columns (or similar that can be mapped):
        - **Date**: Transaction date
        - **Details**: Description of the transaction
        - **AmountCharged**: Transaction amount
        - **Debit/Credit**: Indicates whether it's an expense (Debit) or payment (Credit)
        
        ### Working with PDFs
        PDF support is experimental and works best with PDFs that have clearly defined tables.
        You may need to manually map columns after uploading a PDF.
        """)

if __name__ == "__main__":
    main()
