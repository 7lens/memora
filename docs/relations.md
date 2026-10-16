---
type: Relation Catalog
title: Relation types
description: Initial typed relations for the knowledge graph.
brain:
  relation_types:
    belongs_to: An entity belongs to a project or repository.
    depends_on: An entity needs another entity.
    supports: Evidence or an idea supports another entity.
    contradicts: Two claims or decisions conflict.
    replaces: A newer entity replaces an older entity.
    explains: An entity explains another entity.
    documents: A document describes another entity.
    implements: A repository or system implements an entity.
    validates: An entity provides a check for another entity.
    derived_from: An entity uses another source or entity.
    observes: An observation describes an entity or relation. Derived from its subject.
    related_to: Two entities have a useful link.
---
# Relation types

Add a definition before you use a new relation type. Keep the type name in lowercase.

Project and repository scope also creates a `belongs_to` graph edge. Keep scope fields as the source of truth for these edges.
