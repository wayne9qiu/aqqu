"""
A module for simple query translation.

Copyright 2015, University of Freiburg.

Elmar Haussmann <haussmann@cs.uni-freiburg.de>

"""
from answer_type.answer_type_guesser import AnswerTypeIdentifier
from .pattern_matcher import QueryCandidateExtender, QueryPatternMatcher, get_content_tokens
from entity_linker.entity_index import EntityIndex
import logging
from . import ranker
import time
from corenlp_parser.parser import CoreNLPParser
import globals
import collections
import sparql_backend.loader

logger = logging.getLogger(__name__)

class Query:
    """
    A query that is to be translated.
    """

    def __init__(self, text):
        self.query_text = text.lower()
        self.target_type = None
        self.query_tokens = None
        self.query_content_tokens = None
        self.identified_entities = None
        self.relation_oracle = None
        self.is_count_query = False
        self.identify_count_query(self.query_text)

    def identify_count_query(self, text):
        """
        Simple check for determining if we are asked for a count
        TODO(schnelle) this should probably be handled by the AnswerTypeIdentifier
        """
        how_many = "how many"
        in_how_many = "in how many"
        if text.startswith(how_many):
            self.is_count_query = True
        elif text.startswith(in_how_many):
            self.is_count_query = True

class QueryTranslator(object):

    def __init__(self, backend,
                 query_extender,
                 entity_linker,
                 parser,
                 scorer,
                 entity_index,
                 answer_type_identifier):
        self.backend = backend
        self.query_extender = query_extender
        self.entity_linker = entity_linker
        self.parser = parser
        self.scorer = scorer
        self.entity_index = entity_index
        self.answer_type_identifier = answer_type_identifier
        self.query_extender.set_parameters(scorer.get_parameters())

    @staticmethod
    def init_from_config():
        config_params = globals.config
        backend_module_name = config_params.get("Backend", "backend")
        backend = sparql_backend.loader.get_backend(backend_module_name)
        query_extender = QueryCandidateExtender.init_from_config()
        parser = CoreNLPParser.init_from_config()
        scorer = ranker.SimpleScoreRanker('DefaultScorer')
        entity_index = EntityIndex.init_from_config()
        entity_linker = scorer.parameters.\
                entity_linker_class.init_from_config(
                        scorer.get_parameters(),
                        entity_index)
        answer_type_identifier = AnswerTypeIdentifier.init_from_config()
        return QueryTranslator(backend, query_extender,
                               entity_linker, parser, scorer, entity_index,
                               answer_type_identifier)

    def set_scorer(self, scorer):
        """Sets the parameters of the translator.

        :type scorer: ranker.Ranker
        :return:
        """
        self.scorer = scorer
        params = scorer.get_parameters()
        if type(self.entity_linker) != params.entity_linker_class:
            self.entity_linker = params.entity_linker_class.init_from_config(
                            params,
                            self.entity_index)

        self.query_extender.set_parameters(params)

    def get_scorer(self):
        """Returns the current parameters of the translator.
        """
        return self.scorer

    def translate_query(self, query_text):
        """
        Perform the actual translation.
        :param query_text:
        :param relation_oracle:
        :return:
        """
        # Parse query.
        logger.info("Translating query: %s." % query_text)
        start_time = time.time()
        # Parse the query.
        query = self.parse_and_identify_entities(query_text)
        # Identify the target type.
        self.answer_type_identifier.identify_target(query)
        # Set the relation oracle.
        query.relation_oracle = self.scorer.get_parameters().relation_oracle
        # Get content tokens of the query.
        query.query_content_tokens = get_content_tokens(query.query_tokens)
        # Match the patterns.
        pattern_matcher = QueryPatternMatcher(query,
                                              self.query_extender,
                                              self.backend)
        ert_matches = []
        ermrt_matches = []
        ermrert_matches = []
        ert_matches = pattern_matcher.match_ERT_pattern()
        ermrt_matches = pattern_matcher.match_ERMRT_pattern()
        ermrert_matches = pattern_matcher.match_ERMRERT_pattern()
        duration = (time.time() - start_time) * 1000
        logging.info("Total translation time: %.2f ms." % duration)
        return ert_matches + ermrt_matches + ermrert_matches

    def parse_and_identify_entities(self, query_text):
        """
        Parses the provided text and identifies entities.
        Returns a query object.
        :param query_text:
        :return:
        """
        # Parse query.
        parse_result = self.parser.parse(query_text)
        tokens = parse_result.tokens
        # Create a query object.
        query = Query(query_text)
        query.query_tokens = tokens
        entities = self.entity_linker.identify_entities_in_tokens(
            query.query_tokens)
        query.identified_entities = entities
        return query

    def translate_and_execute_query(self, query, n_top=200):
        """
        Translates the query and returns a list
        of namedtuples of type TranslationResult.
        :param query:
        :return:
        """
        TranslationResult = collections.namedtuple('TranslationResult',
                                                   ['query_candidate',
                                                    'query_result_rows'],
                                                   verbose=False)
        # Parse query.
        results = []
        num_sparql_queries = self.backend.num_queries_executed
        sparql_query_time = self.backend.total_query_time
        queries_candidates = self.translate_query(query)
        translation_time = (self.backend.total_query_time - sparql_query_time) * 1000
        num_sparql_queries = self.backend.num_queries_executed - num_sparql_queries
        avg_query_time = translation_time / (num_sparql_queries + 0.001)
        logger.info("Translation executed %s queries in %.2f ms."
                    " Average: %.2f ms." % (num_sparql_queries,
                                            translation_time, avg_query_time))
        logger.info("Ranking %s query candidates" % len(queries_candidates))
        ranker = self.scorer
        ranked_candidates = ranker.rank_query_candidates(queries_candidates)
        logger.info("Fetching results for all candidates.")
        sparql_query_time = self.backend.total_query_time
        n_total_results = 0
        if len(ranked_candidates) > n_top:
            logger.info("Truncating returned candidates to %s." % n_top)
        for query_candidate in ranked_candidates[:n_top]:
            query_result = query_candidate.get_result(include_name=True)
            # Sometimes virtuoso just doesn't process a query
            if not query_result:
                continue
            n_total_results += sum([len(rows) for rows in query_result])
            result = TranslationResult(query_candidate, query_result)
            results.append(result)
        # This assumes that each query candidate uses the same SPARQL backend
        # instance which should be the case at the moment.
        result_fetch_time = (self.backend.total_query_time - sparql_query_time) * 1000
        avg_result_fetch_time = result_fetch_time / (len(results) + 0.001)
        logger.info("Fetched a total of %s results in %s queries in %.2f ms."
                    " Avg per query: %.2f ms." % (n_total_results, len(results),
                                                  result_fetch_time, avg_result_fetch_time))
        logger.info("Done translating and executing: %s." % query)
        return results




if __name__ == '__main__':
    logger.warn("No MAIN")

