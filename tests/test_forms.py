from playwright.sync_api import Page, expect

def test_add_element_form_opens(page: Page):
    page.goto("/")
    
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

def test_a_table_name_reads_as_one_thing_in_a_title():
    """The suggestion form said "Suggested activitie" for want of a real singular."""
    from pantograph.form_gen import singular

    assert singular("activities") == "activity"
    assert singular("initiatives") == "initiative"
    assert singular("contracts") == "contract"
    assert singular("organisations") == "organisation"
    assert singular("people") == "person"
    assert singular("processing_activities") == "processing_activity"
    assert singular("addresses") == "address"
    # Not plural, so left alone rather than mangled.
    assert singular("status") == "status"
    assert singular("glass") == "glass"
