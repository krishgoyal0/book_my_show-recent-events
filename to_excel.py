from openpyxl import Workbook
from datetime import datetime

def convert_report_to_excel(input_file, output_file):
    # Create a new workbook and select the active worksheet
    wb = Workbook()
    ws = wb.active
    ws.title = "Event Report"

    # Read the input file
    with open(input_file, 'r', encoding='utf-8') as file:
        content = file.read()

    # Initialize variables
    current_section = None
    events = []
    current_event = {}

    # Parse the content
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        # Detect section changes
        if line.startswith('==='):
            if 'Newly added events' in line:
                current_section = 'added'
            elif 'Removed events' in line:
                current_section = 'removed'
            elif 'New Events Summary' in line:
                current_section = 'summary'
            continue
            
        # Process events in added/removed sections
        if line.startswith('- ') and current_section in ['added', 'removed']:
            if current_event:  # Save previous event if exists
                events.append(current_event)
            event_name = line[2:]
            current_event = {
                'name': event_name,
                'url': '',
                'type': 'Added' if current_section == 'added' else 'Removed',
                'venue': 'N/A',
                'date': 'N/A'
            }
        elif line.startswith('  URL:') and current_event:
            current_event['url'] = line.replace('URL:', '').strip()
            
        # Process events in summary section
        elif current_section == 'summary' and line[0].isdigit() and '. ' in line:
            if current_event:  # Save previous event if exists
                events.append(current_event)
            event_name = line.split('. ', 1)[1]
            current_event = {
                'name': event_name,
                'url': '',
                'type': 'New Summary',
                'venue': 'N/A',
                'date': 'N/A'
            }
        elif current_section == 'summary' and line.startswith('   Venue:'):
            current_event['venue'] = line.replace('Venue:', '').strip()
        elif current_section == 'summary' and line.startswith('   Date:'):
            current_event['date'] = line.replace('Date:', '').strip()
        elif current_section == 'summary' and line.startswith('   URL:'):
            current_event['url'] = line.replace('URL:', '').strip()

    # Add the last event if exists
    if current_event:
        events.append(current_event)

    # Write headers
    headers = ['Event Name', 'Type', 'Venue', 'Date', 'URL']
    ws.append(headers)

    # Write event data
    for event in events:
        row = [
            event['name'],
            event['type'],
            event['venue'],
            event['date'],
            event['url']
        ]
        ws.append(row)

    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2
        ws.column_dimensions[column_letter].width = adjusted_width

    # Save the workbook
    wb.save(output_file)
    print(f"Excel file saved as {output_file}")

# Example usage
input_file = 'event_report_2025-06-05.txt'
output_file = 'event_report_2025-06-05.xlsx'
convert_report_to_excel(input_file, output_file)