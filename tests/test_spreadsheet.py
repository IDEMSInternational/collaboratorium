import pytest
from playwright.sync_api import Page, expect

# High-fidelity state transition matrix
# Format: (View ID, Sub-tab Name, List of Steps)
# Each Step: (target_entities_list, list_of_expected_pagination_strings)
#   - target_entities_list = None: Keep current/default filter state unchanged
#   - target_entities_list = []: Click the clear-anchor button to empty the filter
#   - target_entities_list = [...]: Clear filter and append each option sequentially via typing
STATE_MATRIX = [
    # Scenario 1: Verify data transitions dynamically between different single entity selections
    (
        "view-degree",
        "activities",
        [
            (["Initiative 2"], ["1 to 3", "of 3"]),
            (["Automated Tester"], ["1 to 3", "of 3"]),
        ]
    ),
    # Scenario 2: Fully express the filter clearing case (Verify baseline default -> cleared "view all")
    (
        "view-degree",
        "activities",
        [
            (None, ["1 to 3", "of 3"]),  # Verify auto-loaded user state
            ([], ["1 to 15", "of 15"]),  # Clear filter completely -> fetches all records
        ]
    ),
    # Scenario 3: Verify multiple target entities accumulate row totals cumulatively
    (
        "view-degree",
        "activities",
        [
            (None, ["of 3"]),
            (["Automated Tester", "Initiative 2"], ["1 to 6", "of 6"]),
        ]
    )
]

@pytest.mark.parametrize("view_id, tab_name, steps", STATE_MATRIX)
def test_spreadsheet_pipeline_state_transitions(page: Page, view_id, tab_name, steps):
    page.goto("http://localhost:8055")
    
    # 1. Select the View ONLY if it is not already active to prevent toggling the panel closed
    view_button = page.locator(f"#{view_id}")
    if "btn-warning" not in view_button.get_attribute("class"):
        view_button.click()
        
    # Expand the filter settings accordion if it is not already open
    accordion_btn = page.locator(".accordion-button", has_text="View and Filter Settings")
    if accordion_btn.get_attribute("aria-expanded") != "true":
        accordion_btn.click()
    
    # 2. Switch to main Spreadsheet layout and focus target table tab
    page.locator(".nav-link", has_text="Spreadsheet").click()
    page.locator(".nav-link", has_text=tab_name.title()).click()
    
    # Target the stable, stationary pagination component panel directly
    pagination_panel = page.locator("[id^='spreadsheet-table-" + tab_name + "'] .ag-paging-panel")
    
    # 3. Sequentially process pipeline steps defined in the matrix configuration profile
    for target_entities, expected_texts in steps:
        
        # If target_entities is None, skip modifications and evaluate current layout state
        if target_entities is not None:
            # Clear existing selections using the distinct anchor button if it's currently rendered
            clear_btn = page.locator("#filter-target-entity > span > a")
            if clear_btn.is_visible():
                clear_btn.click()
                
            # If an explicit selection array is designated, append items sequentially via keyboard input
            if target_entities:
                for entity in target_entities:
                    # Focus the container, type the match value, and press Enter to commit selection
                    page.locator("#filter-target-entity").click()
                    page.keyboard.type(entity, delay=50)
                    page.keyboard.press("Enter")
                    page.keyboard.press("Escape")
                    
        # 4. Strict Validation: Assert every item in the text list is visible in the pagination model
        for expected_text in expected_texts:
            expect(pagination_panel).to_contain_text(expected_text, timeout=5000)