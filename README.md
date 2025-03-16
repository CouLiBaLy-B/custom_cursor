# README for Cursor Project Generator

## Cursor Project Generator

The Cursor Project Generator is an advanced tool designed to automate the creation of software project structures using AI models. It streamlines the process of setting up new projects by generating necessary files, folders, and configurations based on a given description.

## Features

- Generates complete project structures from descriptions using AI models.
- Supports interaction with Ollama API or CLI for text generation.
- Caches responses to improve performance and reduce API calls.
- Provides functionality for creating virtual environments and initializing Git repositories.
- Offers template management for reusing project structures.
- Includes error handling and logging for a smooth user experience.

## Requirements

- Python 3.10 or higher
- Access to Ollama API or CLI
- Required Python packages: requests, tqdm, yaml, hashlib, logging, argparse, concurrent.futures

## Installation

Ensure Python 3.6+ is installed on your system.
Clone the repository or download the source code.
Install the required Python packages using pip:

```bash
pip install requests tqdm pyyaml
```

Configure the Ollama API or CLI according to the provided documentation.

## Usage

To use the Cursor Project Generator, run the script with the desired command:

```bash
python main.py [command] [options]
```

Available commands include:

- create: Create a new project based on a description.
- list-templates: List available project templates.
- save-template: Save an existing project as a template for future use.
- analyze: Analyze a project to identify potential issues.
- fix-file: Correct a specific file based on an error description.
- fix-project: Automatically correct identified issues in a project.

## Examples of Usage

### Creating a New Project

```bash
python main.py create "A web application for a bookstore"
```

### Listing Templates

```bash
python main.py list-templates
```

### Saving a Project as a Template

```bash
python main.py save-template ./projects/bookstore_project "bookstore_template"
```

### Analyzing a Project

```bash
python main.py analyze ./projects/bookstore_project --output analysis.json
```

### Fixing a Specific File

```bash
python main.py fix-file ./projects/bookstore_project/app/models/user.py "The User model does not handle password validation correctly"
```

### Fixing an Entire Project

```bash
python main.py fix-project ./projects/bookstore_project
```

## Configuration

The tool can be configured using a JSON or YAML configuration file. The default configuration can be overridden by environment variables prefixed with CURSOR*GEN*.

## Logging

Logs are written to cursor_project_creator.log and the console, providing detailed information about the tool's operations and any errors encountered.

## Contributing

Contributions to the Cursor Project Generator are welcome. Please feel free to submit pull requests or create issues for bugs and feature requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Credits

Developed by Ibrahim with the support of the Ollama API team.
