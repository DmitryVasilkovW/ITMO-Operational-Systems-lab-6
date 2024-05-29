import yaml


def parse_directory_listing(yaml_file):
    try:
        with open(yaml_file, 'r') as file:
            data = yaml.safe_load(file)

            directory_listing_block = data.get('DIRECTORY_LISTING', [])

            directory_listing_commands = []
            for command in directory_listing_block:
                if isinstance(command, dict):
                    for key, value in command.items():
                        if key == 'echo':
                            directory_listing_commands.append(value.strip())
                elif isinstance(command, str):
                    directory_listing_commands.append(command.strip())

            return directory_listing_commands
    except FileNotFoundError:
        print("Файл не найден.")
        return []
    except yaml.YAMLError as exc:
        print(exc)
        return []

