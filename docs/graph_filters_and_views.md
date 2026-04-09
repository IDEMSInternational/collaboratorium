# Collaboratorium Graph View Configuration & Filter System

The Collaboratorium graph utilizes a **Composable Filter Pipeline** architecture. Instead of hardcoding graph traversal logic (like finding downstream children or upstream parents) into the application's core codebase, traversals are defined dynamically in `config.yaml`. 

This allows administrators to create complex, highly customized graph views without writing any Python code.

---

## 1. How the Pipeline Works

When a user selects a view (e.g., "Downstream View") and chooses some starting nodes (e.g., a specific Initiative), the system feeds those initial **"Seed Nodes"** into a sequential pipeline.

The pipeline is an ordered list of **Filters**. Each filter receives the current set of nodes, performs an action (like crawling relationships, removing certain node types, or filtering by dates), and passes the resulting set of nodes to the next filter.

The final set of nodes at the end of the pipeline determines exactly what is rendered on the screen.

---

## 2. Filter Reference Guide

Here are the discrete filter operations available to use in your `config.yaml` pipelines.

### `TraversalFilter`
Crawls the graph's edges starting from the current nodes.
* **`direction`**: Which way to crawl. Accepts `parents` (up/in-edges), `children` (down/out-edges), or `both`.
* **`max_depth`**: How far to crawl. Accepts an integer (e.g., `1`, `3`) or `'infinity'` to crawl until the graph ends.
* **`allowed_types`**: A list of node types (e.g., `['initiatives', 'activities']`). The crawler will *only* traverse into these specific types of nodes.
* **`accumulate`**: (Boolean, default `false`). If `true`, the output includes the starting nodes *plus* the newly reached nodes. If `false`, the output *only* includes the newly reached nodes.

### `PropertyFilter`
Removes nodes based on their internal data properties (e.g., dates, numbers).
* **`target_type`**: The node type to apply the filter to (e.g., `'activities'`). Nodes of other types pass through unaffected.
* **`property_key`**: The property to check (e.g., `'start_date'`).
* **`min_val`**: Drops the node if its property is less than this value.
* **`max_val`**: Drops the node if its property is greater than this value.

### `NodeTypeFilter`
Strictly removes any nodes that do not match the allowed types. Used to clean up a graph before rendering.
* **`allowed_types`**: A list of tables (e.g., `['people', 'initiatives']`).

### `SaveSet`
Saves the *current* state of the nodes into memory so you can recall them later in the pipeline.
* **`set_name`**: A string identifier (e.g., `'base_initiatives'`).

### `Union`
Merges the *current* state of the nodes with a previously saved set.
* **`with_set`**: The name of the set to merge with. 
*(Note: The system automatically saves your initial starting nodes as `'seed_nodes'` at the very beginning of the pipeline).*

---

## 3. Dynamic UI Variables

You can map pipeline parameters directly to the UI using the `$` prefix. When the view runs, it will inject the user's current selections from the frontend.

Available dynamic variables:
* **`$start_date`**: From the date-range picker.
* **`$end_date`**: From the date-range picker.
* **`$degree`**: From the degree number input.
* **`$degree_inout`**: From the direction checkboxes.
* **`$degree_types`**: From the node-type checkboxes.

*Example:* `min_val: $start_date`

---

## 4. User Guide: Creating a New View

To create a new view, open your `config.yaml` and navigate to the `views:` section. 

A view consists of four parts:
1. **Identifier:** The YAML key (e.g., `view-custom`).
2. **Metadata:** `name` (Display text), `icon` (Bootstrap icon class), and `layout` (Cytoscape layout algorithm).
3. **Pipeline:** The ordered list of filters.
4. **Active Filters:** Which UI panels to show the user on the left-hand sidebar.

### Example: "Contract Impact View"
**Goal:** A stakeholder wants to select a Contract, immediately find everything that contract funded, and then trace every single child activity resulting from that funding, filtered by a specific year.

```yaml
  view-contract-impact:
    name: "Contract Impact View"
    icon: "bi-file-earmark-text"
    layout: "dagre"
    pipeline:
      # Step 1: Ensure we are only starting with Contracts or Organisations
      - filter: NodeTypeFilter
        allowed_types: ['contracts', 'organisations']
      
      # Step 2: Save the funders so we don't lose them during traversal
      - filter: SaveSet
        set_name: "funders"
        
      # Step 3: Jump exactly 1 step to find direct work funded by the contract
      - filter: TraversalFilter
        direction: both
        max_depth: 1
        allowed_types: ['initiatives', 'activities']
        accumulate: true
        
      # Step 4: Cascade down infinitely to find all sub-work
      - filter: TraversalFilter
        direction: children
        max_depth: infinity
        allowed_types: ['initiatives', 'activities']
        accumulate: true
        
      # Step 5: Filter the resulting activities by the user's date range UI
      - filter: PropertyFilter
        target_type: 'activities'
        property_key: 'start_date'
        min_val: $start_date
        max_val: $end_date
        
      # Step 6: Ensure the original funders are added back to the final graph
      - filter: Union
        with_set: "funders"
        
    # Define which UI elements the user sees for this view
    active_filters:
      target-entity:
        parameters:
          source_tables: [contracts, organisations] # Only allow selecting contracts/orgs
      date-range: null # Show the date picker

### Tips for Pipeline Design
1. **Always think about what nodes are "Current":** When a `TraversalFilter` runs with `accumulate: false`, the starting nodes are left behind. If you want to keep them, use `accumulate: true` or use `SaveSet` and `Union`.
2. **Use `seed_nodes`:** You don't need to manually save the user's initial selection. `filter: Union` with `with_set: "seed_nodes"` will always bring them back.
3. **The "All Settings" Mode:** If a pipeline array is empty (`pipeline: []`), the backend will skip traversal and return the entire graph. The "All Filters & Settings" button relies on this to act as a global sandbox.
```