import pytest
from playwright.sync_api import Page, expect

def test_clearing_target_entity_updates_grid_pagination(page: Page):
    page.goto("http://localhost:8055")
    
    # 1. Expand the filters panel
    page.locator(".accordion-button", has_text="View and Filter Settings").click()
    
    dropdown = page.locator("#filter-target-entity")
    expect(dropdown).to_contain_text("Automated Tester", timeout=5000)
    
    # 2. Go to the Spreadsheet -> Activities tab
    page.locator(".nav-link", has_text="Spreadsheet").click()
    page.locator(".nav-link", has_text="Activities").click()
    
    # --- BULLETPROOF AG GRID SELECTOR ---
    # We use the prefix selector to find the grid, regardless of its dynamic timestamp ID.
    # Then we target the exact pagination text span.
    pagination_panel = page.locator("[id^='spreadsheet-table-activities'] .ag-paging-panel:visible")
    
    # 3. INITIAL LOAD CHECK
    # We expect exactly 3 activities linked to User 1.
    # The text should be "1 to 3 of 3"
    expect(pagination_panel).to_contain_text("of 3", timeout=5000)
    
    # 4. CLEAR THE FILTER
    page.locator("#filter-target-entity > span > a").click()
    
    expect(dropdown).not_to_contain_text("Automated Tester")
    
    # 5. THE BUG ASSERTION: SPREADSHEET MUST UPDATE
    expect(pagination_panel).not_to_contain_text("of 3", timeout=5000)
    expect(pagination_panel).to_contain_text("of 15", timeout=5000)
    