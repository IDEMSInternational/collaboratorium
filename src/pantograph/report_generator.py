import re
import json
from pantograph import provenance
from pantograph.settings import public_url
from pantograph.db import get_all_provenance, get_dropdown_options, get_relation_links

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

def _provenance_for(node, provenance_by_row):
    """
    The provenance stored against the exact row this node was built from.

    Matched on the version as well as the id, so a report rendered from an older
    version never borrows the newer version's claims.
    """
    properties = node.get('properties', {}) or {}
    try:
        record_id = int(str(node['id']).split('-')[-1])
        version = int(properties.get('version'))
    except (TypeError, ValueError):
        return {}
    return provenance_by_row.get((node['type'], record_id, version), {})

# Placeholders the deployment fills in, not the record. They win over a column
# of the same name, so a template means the same thing whatever the schema.
BASE_URL = 'base_url'

def generate_markdown_report(report_cfg, elements, base_url=None):
    """
    Takes the YAML configuration and filtered Graph elements to yield a Markdown report.

    ``{base_url}`` in a template is the deployment's public address, so a link
    such as ``[🔗]({base_url}#edit/initiatives/{id})`` still leads back to the
    record once the markdown is pasted somewhere else. ``base_url`` defaults to
    :func:`pantograph.settings.public_url`; pass ``""`` for links relative to
    the page the report is shown on.
    """
    if base_url is None:
        base_url = public_url()
    nodes_dict = {e['data']['id']: e['data'] for e in elements if 'source' not in e['data']}
    edges = [e['data'] for e in elements if 'source' in e['data']]
    
    people_opts = get_dropdown_options('people', 'id', 'name')
    people_map = {row['value']: row['label'] for row in people_opts} if people_opts else {}
    
    # Query all active relationship links securely processed through the database layer
    act_people_df = get_relation_links('activity_people_links', 'activity_id', 'person_id')

    # The export is the artefact a regulator is handed, so it has to say which
    # of its assertions anyone here actually made.
    provenance_by_row = get_all_provenance()

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

        # Context-aware name resolution triggers
        if node['type'] == 'initiatives':
            resp_id = node.get('properties', {}).get('responsible_person')
            if resp_id and resp_id in people_map:
                format_dict['responsible_person'] = people_map[resp_id]
            else:
                format_dict['responsible_person'] = "None"
                
        if node['type'] == 'activities':
            act_id = int(node['id'].split('-')[-1])
            p_ids = act_people_df[act_people_df['activity_id'] == act_id]['person_id'].tolist()
            names = [people_map[pid] for pid in p_ids if pid in people_map]
            format_dict['linked_people'] = ", ".join(names) if names else "None"

        format_dict[BASE_URL] = base_url

        row_provenance = _provenance_for(node, provenance_by_row)

        def safe_replace(match):
            key = match.group(1)
            if key == BASE_URL:
                # Part of a link target, where a provenance note would break it.
                return base_url
            val = format_dict.get(key, "")
            text = str(val) if val is not None else ""
            if not text:
                # A bare origin note against an empty value says less than it
                # implies, so there is nothing to annotate.
                return text
            return text + provenance.annotation(row_provenance.get(key))

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