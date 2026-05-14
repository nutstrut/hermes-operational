def json_path_values(obj, path):
    parts = path.split(".")
    current = [obj]

    for part in parts:
        nxt = []
        is_array = part.endswith("[]")
        key = part[:-2] if is_array else part

        for item in current:
            if isinstance(item, dict) and key in item:
                val = item[key]

                if is_array and isinstance(val, list):
                    nxt.extend(val)
                else:
                    nxt.append(val)

        current = nxt

    return current
