import pytest
from playwright.sync_api import Page, expect

# Format: (View ID, First Entity Label, Tab ID, Second Entity Label, Expected Text to Disappear)
STATE_MATRIX = [
    ("view-downstream", "initiatives-1", "subtab-activities", "initiatives-2", "Activity: Build Panel"),
]

@pytest.mark.parametrize("view_id, start_entity, sheet_tab, next_entity, expected_text", STATE_MATRIX)
def test_spreadsheet_data_refresh_on_filter_change(page: Page, view_id, start_entity, sheet_tab, next_entity, expected_text):
    page.goto("http://localhost:8055")
    
    # 1. Select the View
    page.click(f"#{view_id}")
    page.locator(".accordion-button", has_text="View and Filter Settings").click()
    
    # 2. Select initial entity
    page.locator("#filter-target-entity").click()
    page.keyboard.type(start_entity, delay=50)
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    
    # 3. Switch to Spreadsheet Tab and verify initial data loads
    page.locator(".nav-link", has_text="Spreadsheet").click()
    subtab_label = sheet_tab.split('-')[1].title() 
    page.locator(".nav-link", has_text=subtab_label).click()
    
    # Assert the initial row is visible
    grid = page.locator(f"[id^='spreadsheet-table-{sheet_tab.split('-')[1]}']")
    expect(grid).to_contain_text(expected_text, timeout=5000)
    
    # 4. Change target entity while staying on the spreadsheet
    page.locator("#filter-target-entity").click()
    page.keyboard.press("Backspace")
    page.keyboard.type(next_entity, delay=50)
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")

    # 5. Assert the old text disappears because the new entity doesn't have it
    # If the bug exists, this assertion will fail because Dash failed to re-render the rows!
    expect(page.locator("#spreadsheet-container")).not_to_contain_text(expected_text, timeout=5000)