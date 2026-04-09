Notes to demo the new filters/views system.

## Demo Downstream View

- `RapidPro Server Hosting` : We can see what is impacted if we decided to no longer host RapidPro
- Person : we can see what projects could be impacted by e.g. maternity/paternity leave so we can prepare, looking at direct responsibilities and downstream initiatives 

## Demo use of Advanced Pipeline Editor
What is actually being done? We can see the data pipeline under Advanced Pipeline Editor.
There are these traversal filters which can be directional, can have bounded depth, and can filter types.
We can save these for later to combine with set unions, and do other filtering

### What if we want to see the people impacted?
At the bottom of the filters, we can add a filter that finds all people related to the included nodes:
```yaml
- filter: TraversalFilter
  direction: both
  max_depth: 1
  allowed_types:
  - people
```

### Context
What if we want to see the context of `Initiatives: CrisisText?

We can add this to the top of the filters:

```yaml
- filter: TraversalFilter
  direction: both
  max_depth: 1
  allowed_types:
  - initiatives
```

## Demo of Contract Impact View
- `McKnight Foundation Research...` This is the most well documented contract in the system