import pandas as pd
import re

def clean_csv_dates(input_file, output_file):
    """
    Clean and fix date formats in the CSV file.
    """
    # Read the CSV
    df = pd.read_csv(input_file)
    
    # Function to fix individual date entries
    def fix_date(date_str):
        # Check if this is already a valid date string
        try:
            # First check mm/dd/yy format (American style)
            result = pd.to_datetime(date_str, errors='coerce')
            if not pd.isna(result):
                return result.strftime('%m/%d/%Y')
                
            # Handle DD/MM/YYYY format (common in your data)
            result = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
            if not pd.isna(result):
                return result.strftime('%m/%d/%Y')
                
            # Handle specific edge cases
            if '31/11' in date_str:  # November has 30 days
                date_str = date_str.replace('31/11', '30/11')
                return pd.to_datetime(date_str, dayfirst=True).strftime('%m/%d/%Y')
                
            if '13/23' in date_str:  # Likely meant to be 13/12 (December)
                date_str = date_str.replace('13/23', '13/12')
                return pd.to_datetime(date_str, dayfirst=True).strftime('%m/%d/%Y')
            
            # Add more specific rules as needed
                
            return None  # Can't fix the date
            
        except Exception:
            return None  # Can't fix the date
    
    # Apply the fix to all dates
    df['Date'] = df['Date'].apply(fix_date)
    
    # Remove any rows with dates that couldn't be fixed
    if df['Date'].isna().any():
        print(f"Warning: Removed {df['Date'].isna().sum()} rows with invalid dates")
        df = df.dropna(subset=['Date'])
    
    # Write the cleaned data
    df.to_csv(output_file, index=False)
    print(f"Cleaned data saved to {output_file}")
    
    return df

# Example usage:
# clean_df = clean_csv_dates('your_input.csv', 'cleaned_output.csv')