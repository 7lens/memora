---
type: Technical Glossary
title: Technical terms
description: Defined terms for the memory system.
brain:
  terms:
    observation:
      definition: A dated claim about an entity or relation with a stated basis.
      subject: Knowledge
      use: Technical noun. Distinguish direct, reported, and inferred findings.
    workspace:
      definition: A separate local memory space with its own notes and index.
      subject: Storage
      use: Technical noun. A local space does not enforce remote team permissions.
    projection:
      definition: Selected content prepared for a specified sharing destination.
      subject: Exchange
      use: Technical noun. Exclude private history and task progress.
    MCP:
      definition: A protocol that lets an agent call tools from another process.
      subject: Software
      use: Technical noun. Use for the local memory connector.
    receipt:
      definition: A record that identifies the context returned by a tool call.
      subject: Agent memory
      use: Technical noun. Do not use it as proof of model understanding.
    embedding:
      definition: A numeric vector that represents text for similarity search.
      subject: Search
      use: Technical noun. Use for disposable local search vectors.
    bundle:
      definition: A versioned package of private notes, relations, and events.
      subject: File formats
      use: Technical noun. Use for private memory export and import.
    external reference:
      definition: A typed link from a note to an entity in another system.
      subject: Data
      use: Technical noun. Do not use it as an access grant.
    agent:
      definition: A software tool that performs tasks from instructions.
      subject: Software
      use: Technical noun. Use for a tool that can read and change memory.
    brain:
      definition: The shared knowledge repository and its local tools.
      subject: Agent memory
      use: Technical noun. Use for this memory system.
    knowledge graph:
      definition: A set of entities with relations between them.
      subject: Data
      use: Technical noun. Use for the memory graph.
    node:
      definition: An entity in the graph.
      subject: Data
      use: Technical noun. Use in graph descriptions.
    edge:
      definition: A directed relation between two graph entities.
      subject: Data
      use: Technical noun. Use in graph descriptions.
    checkpoint:
      definition: A stored record of task progress, memory candidates, and ideas.
      subject: Agent memory
      use: Technical noun. Use for task continuity. Do not use it as a confirmed knowledge note.
    frontmatter:
      definition: YAML metadata at the start of a Markdown file.
      subject: File formats
      use: Technical noun. Use for note metadata.
    worktree:
      definition: A Git work directory that shares repository data with another directory.
      subject: Git
      use: Technical noun. Use for a Git worktree.
    metadata:
      definition: Structured fields that describe an entity.
      subject: Data
      use: Technical noun. Use for note fields.
    score:
      definition: A number that indicates the evidence level for a note.
      subject: Agent memory
      use: Technical noun. Use only for the evidence score.
    health report:
      definition: A list of notes and relations that need review.
      subject: Agent memory
      use: Technical noun. Use for the output of the health command.
    repository:
      definition: A Git directory that stores source code or documents.
      subject: Git
      use: Technical noun. Use for a registered repository.
    CLI:
      definition: A command-line interface.
      subject: Software
      use: Technical noun. Use for the brain commands.
    Markdown:
      definition: A text format with document structure and links.
      subject: File formats
      use: Product name and technical noun.
    YAML:
      definition: A structured text format for metadata.
      subject: File formats
      use: Product name and technical noun.
    JSON:
      definition: A structured text format for data exchange.
      subject: File formats
      use: Product name and technical noun.
    HTML:
      definition: A document format for browser interfaces.
      subject: File formats
      use: Technical noun.
    SQLite:
      definition: The local database engine for the disposable index.
      subject: Software
      use: Product name.
    OKF:
      definition: Open Knowledge Format.
      subject: File formats
      use: Standard name.
    STE:
      definition: ASD-STE100 Simplified Technical English.
      subject: Technical language
      use: Standard name.
    PKCE:
      definition: An authorization code check that binds a login request to its token exchange.
      subject: Authentication
      use: Technical noun. Keep the acronym unchanged.
    cursor:
      definition: A saved position in a sequence of remote changes.
      subject: Synchronization
      use: Technical noun. Use for incremental transfer only.
    canonicalization:
      definition: The conversion of equivalent JSON values to one byte representation.
      subject: Data exchange
      use: Technical noun. Use with the defined exchange algorithm.

    inspector:
      definition: A panel that shows one note and its details.
      subject: User interface
      use: Technical noun. Use for the note detail panel.
    benchmark:
      definition: A fixed set of tasks used to compare measured results.
      subject: Evaluation
      use: Technical noun. State the task set and conditions.
    KPI:
      definition: A key performance indicator with a specified measure and denominator.
      subject: Evaluation
      use: Technical noun. Do not use an evidence score as a task success measure.
    rubric:
      definition: A fixed set of criteria used to assess a response.
      subject: Evaluation
      use: Technical noun. Define the criteria before the run.
    baseline:
      definition: A comparison condition in an experiment.
      subject: Evaluation
      use: Technical noun. Identify which context and tools it receives.
    bootstrap:
      definition: A method that samples recorded units with replacement to estimate variation.
      subject: Statistics
      use: Technical noun. State the sampled unit and the limits of the estimate.
    corpus:
      definition: The set of source notes used in a specified study or search.
      subject: Evaluation
      use: Technical noun. Identify public synthetic data and private memory separately.
    oracle:
      definition: A comparison condition that receives the notes selected by a fixed task rubric.
      subject: Evaluation
      use: Technical noun. Do not describe it as an available retrieval method.
    token:
      definition: A unit that a model runtime uses to count input or output text.
      subject: Language models
      use: Technical noun. Use the runtime count. Do not equate tokens with bytes.
    theme:
      definition: A set of interface colors for a light or dark display.
      subject: User interface
      use: Technical noun. Use for the light or dark color choice.

    JSON-LD:
      definition: A JSON format for linked data with a term context.
      subject: Data exchange
      use: Standard name. Use version 1.1 and the pinned context.
    PROV-O:
      definition: The W3C ontology for provenance in RDF.
      subject: Provenance
      use: Standard name. Keep publication review separate from source verification.
    provenance:
      definition: The sources, actors, and changes from which a record came.
      subject: Knowledge
      use: Technical noun. A source label does not authenticate an actor.
    conformance:
      definition: Agreement with the stated schema and semantic rules.
      subject: Standards
      use: Technical noun. A test result does not certify a deployment.
    vault:
      definition: A directory of Markdown files that Obsidian can open.
      subject: Data views
      use: Technical noun. Distinguish a snapshot export from a live editable local view.
    schema:
      definition: A set of rules for the shape of structured data.
      subject: Data validation
      use: Technical noun. Apply semantic rules as well as schema checks.
    manifest:
      definition: A record that identifies the contents and version of a package or pilot.
      subject: Data exchange
      use: Technical noun. Keep the exact selected corpus and configuration.
    ingestion:
      definition: The validation and capture of extracted findings as private drafts.
      subject: Agent capture
      use: Technical noun. It does not imply publication or source verification.
    namespace:
      definition: A named boundary for identifiers or authorized content.
      subject: Data
      use: Technical noun. State whether the boundary concerns identity or access.

---
# Technical terms

Each term has one definition, a subject, and a permitted use. This glossary does not replace the STE dictionary.
