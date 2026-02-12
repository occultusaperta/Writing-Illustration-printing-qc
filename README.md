# BookForge - KDP Children's Book Pipeline

A minimal pipeline for creating KDP-ready children's books with automated story generation, illustration, layout, and quality control.

## Features

- **Story Agent**: Generates age-appropriate children's book stories
- **Style Bible Agent**: Creates visual style guide with approval gate
- **Illustrator Agent**: Generates illustrations (Fal/Flux integration ready)
- **Layout Agent**: Creates print-ready PDFs using ReportLab
- **KDP Preflight**: Validates against KDP requirements

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python -m bookforge run --idea "a brave little mouse"
```

### With Options

```bash
# Specify age group
python -m bookforge run --idea "a magical garden" --age-group ages_5_7

# Specify output directory
python -m bookforge run --idea "friends who help each other" --output ./my-book
```

### Age Groups

- `ages_0_3`: Babies and Toddlers
- `ages_3_5`: Preschool (default)
- `ages_5_7`: Early Elementary
- `ages_7_9`: Elementary

## Pipeline Stages

1. **Story Generation**: Creates story structure based on idea and age group
2. **Style Bible**: Defines visual style using knowledge base (directors.json, visual_modes.json)
3. **Illustration**: Generates images for each page (placeholder implementation, Fal/Flux ready)
4. **Layout**: Creates interior and cover PDFs using ReportLab
5. **KDP Preflight**: Validates page count, word count, and file formats

## Knowledge Base

The pipeline uses three knowledge files to inform content creation:

- `bookforge/knowledge/directors.json`: Visual style references (Miyazaki, Wes Anderson, Pixar)
- `bookforge/knowledge/visual_modes.json`: Art styles (watercolor, digital, pencil, collage)
- `bookforge/knowledge/psychology.json`: Age-appropriate content guidelines

All knowledge is loaded into every agent for consistent decision-making.

## Output

The pipeline generates:

- `interior.pdf`: Print-ready interior pages
- `cover.pdf`: Book cover
- `report_[timestamp].json`: Detailed pipeline report
- `report_[timestamp].txt`: Human-readable report
- `illustrations/`: Generated illustrations

## Project Structure

```
bookforge/
├── __init__.py
├── __main__.py              # CLI entry point
├── pipeline.py              # Pipeline orchestrator
├── knowledge_loader.py      # Knowledge base loader
├── agents/
│   ├── __init__.py
│   ├── base_agent.py        # Base agent class
│   ├── story_agent.py       # Story generation
│   ├── style_bible_agent.py # Style guide + approval gate
│   ├── illustrator_agent.py # Image generation
│   ├── layout_agent.py      # PDF creation
│   └── kdp_preflight_agent.py # KDP validation
├── knowledge/
│   ├── directors.json
│   ├── visual_modes.json
│   └── psychology.json
└── output/                  # Generated files
```

## Development

The pipeline is designed to be minimal and extensible:

- Each agent inherits from `BaseAgent` with access to knowledge base
- Agents communicate through a shared context dictionary
- Style Bible agent includes an approval gate (currently auto-approved)
- Illustrator agent has placeholder for Fal/Flux API integration

## Future Enhancements

- [ ] Real Fal/Flux API integration for illustrations
- [ ] Interactive approval gate for style bible
- [ ] Custom illustration references support
- [ ] Advanced layout templates
- [ ] Export to other formats (EPUB, etc.)