import re
import json

def format_subform_data(val_str):
    """Attempts to parse JSON subform data and format it cleanly into Markdown."""
    if not isinstance(val_str, str) or not val_str.strip().startswith('{'):
        return str(val_str)
        
    try:
        data = json.loads(val_str)
        if not isinstance(data, dict):
            return str(val_str)
        
        md_parts = []
        for group_key, group_val in data.items():
            if isinstance(group_val, dict):
                # 1. Extract and format the description text
                desc = group_val.get("description", "")
                if desc:
                    md_parts.append(str(desc))
                
                # 2. Extract and format the attachments table
                attachments = group_val.get("attachments", [])
                if attachments and isinstance(attachments, list):
                    # Filter out empty rows where both name and url are null
                    valid_atts = [a for a in attachments if a.get("url") and a.get("name")]
                    if valid_atts:
                        md_parts.append("\n**Attachments:**")
                        for att in valid_atts:
                            md_parts.append(f"* [{att.get('name')}]({att.get('url')})")
                            
        if md_parts:
            return "\n".join(md_parts)
            
        return str(val_str)
    except (json.JSONDecodeError, TypeError):
        return str(val_str)

def generate_markdown_report(report_cfg, elements):
    """Takes the YAML configuration and filtered Graph elements to yield a Markdown report."""
    nodes_dict = {e['data']['id']: e['data'] for e in elements if 'source' not in e['data']}
    edges = [e['data'] for e in elements if 'source' in e['data']]
    
    adj = {}
    for e in edges:
        s, t = e['source'], e['target']
        adj.setdefault(s, []).append(t)
        adj.setdefault(t, []).append(s)

    def process_node(node_id, level_cfg, visited):
        if node_id in visited: return ""
        visited.add(node_id)
        node = nodes_dict.get(node_id)
        if not node: return ""
        
        template = level_cfg.get("template", "{name}")
        format_dict = {'id': node['id'].split('-')[-1], 'type': node['type'], 'label': node['label']}
        
        # Hydrate properties, formatting subforms nicely if detected
        for k, v in node.get('properties', {}).items():
            if isinstance(v, str) and v.strip().startswith('{'):
                format_dict[k] = format_subform_data(v)
            else:
                format_dict[k] = v

        def safe_replace(match):
            key = match.group(1)
            val = format_dict.get(key, "")
            return str(val) if val is not None else ""
        
        md = re.sub(r'\{([A-Za-z0-9_]+)\}', safe_replace, template)
            
        children_cfg = level_cfg.get("children", [])
        if children_cfg:
            child_cfg = children_cfg[0]
            child_type = child_cfg.get("type")
            
            neighbors = adj.get(node_id, [])
            child_nodes = [nid for nid in neighbors if nid in nodes_dict and nodes_dict[nid].get("type") == child_type]
            
            for cn in child_nodes:
                md += process_node(cn, child_cfg, visited.copy())
        return md

    hierarchy = report_cfg.get("hierarchy", [])
    if not hierarchy: 
        return "No hierarchy defined in config."
    
    root_level = hierarchy[0]
    root_type = root_level.get("type")
    roots = [n['id'] for n in nodes_dict.values() if n.get("type") == root_type]
    
    visited = set()
    full_md = f"# {report_cfg.get('name', 'Report')}\n\n"
    for r in roots:
        full_md += process_node(r, root_level, visited)

    return full_md