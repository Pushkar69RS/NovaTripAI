# NovaTripAI ✈️

> **An AI-powered travel intelligence platform for personalized trip planning, intelligent recommendations, and culturally grounded travel experiences.**

NovaTripAI is a full-stack AI travel assistant designed to make trip planning more personalized, contextual, and useful than conventional itinerary generators.

Instead of treating travel planning as a simple prompt → itinerary problem, NovaTripAI combines **LLM-powered interaction, retrieval-augmented generation (RAG), semantic search, geographic reasoning, itinerary optimization, and cultural storytelling** into a unified travel platform.

The system is built around a modular Python/FastAPI backend with dedicated components for planning, retrieval, language-model interaction, conversational experiences, voice, and travel narratives.

---

## ✨ Features

### 🗺️ Intelligent Trip Planning

Generate structured travel plans based on a user's destination, preferences, duration, interests, and constraints.

The planning engine contains dedicated components for:

* Point-of-interest selection
* Route construction
* Distance calculations
* Transport considerations
* POI filtering and rules
* Clustering of destinations
* Itinerary validation
* Cold-start handling

The planner is organized as an independent module, making it possible to evolve the itinerary engine without coupling it tightly to the presentation layer.

---

### 🤖 AI-Powered Travel Assistant

NovaTripAI integrates language-model capabilities for understanding travel requests and generating natural, contextual responses.

The LLM layer is separated into dedicated components for:

* User-intent intake
* LLM client interaction
* Structured model definitions
* Travel narration
* AI-generated responses

This separation allows the application to combine deterministic travel logic with generative AI instead of relying entirely on an LLM for itinerary generation.

---

### 🔎 Retrieval-Augmented Generation (RAG)

The application includes a dedicated RAG subsystem for grounding travel responses in curated destination information.

The architecture includes:

* Semantic embeddings
* Query retrieval
* Curated travel data
* City-specific data
* POI information
* Chunked knowledge representations

The repository includes structured datasets such as `chunks.json`, `chunks_city.json`, `chunks_curated.json`, and `pois.json`.

The application also warms the local embedding model during startup so that the first retrieval request does not incur the full model initialization delay.

---

### 🪷 Cultural Travel & Katha

Travel is more than a list of locations.

NovaTripAI includes a dedicated **Katha** layer for presenting destinations through cultural and narrative context, helping users understand the stories, heritage, and significance behind the places they visit.

This component is integrated alongside the planner, RAG system, and LLM layer rather than being treated as a separate static information page.

---

### 💬 Conversational Travel Experience

The application includes a dedicated chat subsystem that allows users to interact with the travel assistant conversationally.

This makes it possible to refine a trip through natural conversation rather than repeatedly filling out rigid travel forms.

---

### 🎙️ Voice Interaction

A dedicated voice module provides the foundation for voice-based travel interaction, allowing the platform to move beyond purely text-based travel planning.

---

### 📍 Location-Aware Recommendations

The system's planning architecture incorporates:

* Geographic distance calculations
* POI clustering
* Route generation
* Transportation considerations
* Destination validation

This allows generated itineraries to be structured around practical travel constraints rather than simply producing an arbitrary list of attractions.

---

## 🧠 Architecture

At a high level, NovaTripAI follows a modular architecture:

```text
                        ┌─────────────────────┐
                        │      User           │
                        │ Web / Chat / Voice  │
                        └──────────┬──────────┘
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │    FastAPI Layer    │
                        │   API + Web Pages   │
                        └──────────┬──────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
       ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
       │   Planner   │      │     RAG     │      │     LLM     │
       │             │      │             │      │             │
       │ Routes      │      │ Embeddings  │      │ Intake      │
       │ Distance    │      │ Retrieval   │      │ Narration   │
       │ POIs        │      │ Knowledge   │      │ Responses   │
       │ Transport   │      │             │      │             │
       └──────┬──────┘      └──────┬──────┘      └──────┬──────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │  Travel Experience  │
                        │                     │
                        │ Itinerary           │
                        │ Recommendations     │
                        │ Cultural Katha      │
                        │ Conversational AI   │
                        └─────────────────────┘
```

The main FastAPI application exposes the API and web interface, mounts static assets, and initializes the retrieval subsystem during application startup.

---

## 🛠️ Tech Stack

### Backend

* **Python 3.12+**
* **FastAPI**
* **Uvicorn**
* **Pydantic**
* **Jinja2**

### AI / ML

* **Large Language Models**
* **Sentence Transformers**
* **Semantic Embeddings**
* **Retrieval-Augmented Generation (RAG)**
* **NumPy**

### Database

* **PostgreSQL**
* **pgvector**
* **Psycopg**

### Application & Infrastructure

* REST API architecture
* Modular Python application structure
* Environment-based configuration
* Database migrations
* Automated testing with Pytest
* Code quality with Ruff

The project's dependency configuration specifies Python 3.12+, FastAPI, sentence-transformers, pgvector, PostgreSQL connectivity, Pydantic, Uvicorn, and related tooling.

---

## 📁 Project Structure

```text
NovaTripAI/
│
├── app/
│   ├── api/                # REST API routes
│   │
│   ├── chat/               # Conversational travel assistant
│   │
│   ├── katha/              # Cultural storytelling layer
│   │
│   ├── llm/                # LLM integration and narration
│   │
│   ├── planner/            # Itinerary and route planning engine
│   │   ├── cluster.py
│   │   ├── distance.py
│   │   ├── engine.py
│   │   ├── models.py
│   │   ├── poi_rules.py
│   │   ├── route.py
│   │   ├── transport.py
│   │   └── validate.py
│   │
│   ├── rag/                # Retrieval-Augmented Generation
│   │
│   ├── static/             # Frontend/static assets
│   │
│   ├── templates/          # Web templates
│   │
│   ├── voice/              # Voice interaction
│   │
│   ├── accounts.py         # User/account functionality
│   ├── main.py             # FastAPI application entry point
│   └── web.py              # Web routes
│
├── data/
│   ├── chunks.json
│   ├── chunks_city.json
│   ├── chunks_curated.json
│   ├── pois.json
│   └── verification_report.md
│
├── db/
│   └── migrations/         # Database migrations
│
├── docs/                   # Project documentation
├── scripts/                # Utility/setup scripts
├── tests/                  # Automated tests
│
├── .env.example
├── pyproject.toml
├── uv.lock
└── README.md
```

The repository currently follows this modular structure, separating application logic, datasets, database migrations, documentation, scripts, and tests.

---

## 🚀 Getting Started

### Prerequisites

Make sure you have:

* Python **3.12+**
* PostgreSQL
* `pgvector`
* Git
* An LLM provider/configuration required by your environment

---

### 1. Clone the repository

```bash
git clone https://github.com/Pushkar69RS/NovaTripAI.git
cd NovaTripAI
```

---

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

**Windows**

```powershell
.venv\Scripts\activate
```

**Linux / macOS**

```bash
source .venv/bin/activate
```

---

### 3. Install dependencies

Using pip:

```bash
pip install -e .
```

Or, if you use `uv`:

```bash
uv sync
```

The repository includes a `pyproject.toml` and `uv.lock` for dependency management.

---

### 4. Configure environment variables

Create a local environment file:

```bash
cp .env.example .env
```

On Windows CMD:

```cmd
copy .env.example .env
```

Add the required configuration values to `.env`.

> **Never commit `.env` or API keys to GitHub.**

---

### 5. Configure PostgreSQL

Create the required PostgreSQL database and enable the `pgvector` extension.

Then apply the project's database migrations.

> Database configuration may vary depending on the environment. Refer to the migration files under `db/migrations/` and the environment configuration used by your installation.

---

### 6. Start the application

Run the FastAPI application with:

```bash
uvicorn app.main:app --reload
```

The application will be available at:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/health
```

The application exposes a `/health` endpoint returning the service status.

---

## 🔌 API

The backend is built around FastAPI and exposes application functionality through an API layer under:

```text
/api
```

The application also serves web pages outside the API namespace.

This separation allows the same backend to support both programmatic API access and the web interface.

For interactive API exploration during development, FastAPI provides its standard documentation endpoints:

```text
http://localhost:8000/docs
```

---

## 🧪 Testing

Run the test suite with:

```bash
pytest
```

The project is configured to discover tests from:

```text
tests/
```

and includes Pytest as a development dependency.

---

## 🔍 Data & RAG Pipeline

NovaTripAI uses a retrieval-oriented knowledge layer to improve the relevance of travel responses.

A simplified pipeline is:

```text
Travel Knowledge
      │
      ▼
Data Processing
      │
      ▼
Chunking / Curation
      │
      ▼
Embeddings
      │
      ▼
Vector Retrieval
      │
      ▼
Relevant Context
      │
      ▼
LLM
      │
      ▼
Grounded Travel Response
```

The repository maintains multiple knowledge datasets for general chunks, city-specific information, curated content, and points of interest.

---

## 🧭 Itinerary Generation Pipeline

The itinerary engine is designed around deterministic travel constraints before generating the final experience.

```text
User Preferences
       │
       ▼
Destination / POI Selection
       │
       ▼
POI Filtering
       │
       ▼
Geographic Clustering
       │
       ▼
Distance Calculation
       │
       ▼
Route Construction
       │
       ▼
Transport Consideration
       │
       ▼
Validation
       │
       ▼
Final Itinerary
```

This approach helps reduce impractical itineraries by incorporating geographic and logistical reasoning into the planning process.

---

## 🎯 Project Objectives

NovaTripAI aims to address several limitations of conventional travel-planning tools:

* Generate personalized itineraries rather than generic destination lists
* Incorporate geographic and transportation constraints
* Ground AI responses using curated travel knowledge
* Provide culturally meaningful destination narratives
* Support conversational travel planning
* Create a modular architecture that can evolve with additional AI capabilities

---

## 🔮 Future Improvements

Potential areas for further development include:

* Real-time weather-aware itinerary adaptation
* Live transport and traffic integration
* Hotel and accommodation recommendations
* Budget-aware itinerary optimization
* Multi-city trip planning
* Personalized travel profiles
* More regional and multilingual cultural content
* Advanced voice-based interaction
* Mobile application support
* Production deployment and observability
* More extensive automated evaluation of generated itineraries

---

## 🤝 Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/your-feature
```

3. Make your changes
4. Run the test suite

```bash
pytest
```

5. Commit your changes

```bash
git commit -m "Add: your feature"
```

6. Push the branch

```bash
git push origin feature/your-feature
```

7. Open a Pull Request

---

## 📄 License

Add the project's chosen license here.

If this project is intended to be open source, consider adding an appropriate license file such as `MIT`, `Apache-2.0`, or `GPL-3.0`.

---

## 👨‍💻 Project

**NovaTripAI**
AI-powered travel planning and cultural intelligence platform.

Built with **Python, FastAPI, RAG, semantic search, PostgreSQL/pgvector, and LLMs.**

---

⭐ If you find the project useful, consider giving the repository a star.
