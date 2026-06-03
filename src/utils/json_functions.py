import json


def covert_json_to_dict(file_path: str) -> dict:
    print(file_path)
    with open(file_path, 'r', encoding='utf-8') as json_archive:
        dict_file: dict = json.load(json_archive)
    return dict_file


def convert_dict_to_json(data: dict) -> str:
    data_json = json.dumps(data, indent=4)
    return data_json
