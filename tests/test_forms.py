from playwright.sync_api import Page, expect

def test_add_element_form_opens(page: Page):
    page.goto("http://localhost:8055")
    
    # Click 'Add Element'
    page.click("#btn-add-element")
    expect(page.locator("#editor-popup")).to_be_visible()
    
    # Select 'activities' from the dropdown
    page.locator("#table-selector").click()
    page.keyboard.type("activities", delay=100)
    page.keyboard.press("Enter")
    
    # Verify the form generated the specific Activity fields
    form_container = page.locator("#form-container")
    expect(form_container).to_contain_text("Add Activities", timeout=5000)
    expect(form_container).to_contain_text("Start Date", timeout=5000)