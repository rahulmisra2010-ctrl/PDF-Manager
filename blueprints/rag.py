        except Exception as exc:
            current_app.logger.warning(
                "RAG: failed to apply training examples for doc %s: %s", doc_id, exc
            )
        # Apply training intelligence: fill blank fields and correct incorrect
