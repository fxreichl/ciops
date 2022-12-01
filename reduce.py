#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse

from synthesisManager import Synthesismanager
from utils import Configuration

############################################################################
# The number of inputs of the gates in the specification needs to be less equal then the number of inputs of the gates that shall be synthesised.
############################################################################

if __name__ == "__main__" :

  parser = argparse.ArgumentParser(description="QBF based circuit synthesis")  
  parser.add_argument('specification', metavar='SPEC',help='The specification')
  parser.add_argument('synthesised_circuit', metavar='SYN',help='Available time')
  parser.add_argument('limit', type=int, metavar='LIM',help='The synthesised circuit')
  parser.add_argument('--gs', nargs=1, type=int, help='The number of inputs of the gates')
  parser.add_argument("--aig", action='store_true', help='Synthesise an AIG. Optional argument for generating an aiger output file.')
  parser.add_argument('--aig-out', nargs=1, help='AIG output file')
  parser.add_argument('--abc', action='store_true', help='Use ABC for inprocessing')
  parser.add_argument("--restarts", nargs=1, type=int, help="The number of restarts")
  parser.add_argument('--seed', nargs=1, type=int, help='Set the seed for random number generation')
  parser.add_argument('--syn-mode', choices=['qbf', 'qbf-clausal', 'equivalent', 'rel-qbf', 'rel-sat'], help='The synthesis approach to use')
  # misc
  parser.add_argument('--qbf-solver', choices=['qfun', 'caqe', 'miniqu', 'quabs', 'qute'], help='The solver to use')
  parser.add_argument('--abc-cmds', nargs=2, metavar='ABCCMDS',help='The abc commands to use')
  parser.add_argument("--it", nargs=1, type=int, help='Stop after the given number of iterations')
  parser.add_argument("--sorted", action='store_true', help='The given specification can be considered as sorted')
  # Options for subcircuit selection
  parser.add_argument('--size', nargs=1, type=int, help='Set the initial subcircuit size')
  parser.add_argument("--single-output", action='store_true', help='Only consider subcircuits with a single output')
  # Options for setting timeouts
  parser.add_argument('--dynTO', action='store_false', help='Disable dynamic timeouts')
  parser.add_argument("--qbfTO", nargs=1, type=int, help = "Base timeout for the qbf checks")
  # Disable Symmetry Breaking Constraints
  parser.add_argument('-N', action='store_false',help='Disable Non trivial')
  parser.add_argument('-A', action='store_false',help='Disable All steps')
  parser.add_argument('-R', action='store_false',help='Disable No Reapplication')
  parser.add_argument('-O', action='store_false',help='Disable Ordered steps')
  # Additional options for subcircuit synthesis
  parser.add_argument('--require-reduction', action='store_true', help='Only replace subcircuits by smaller subcircuits')
  parser.add_argument('--cO', action='store_false',help='Disable constants as outputs')
  parser.add_argument('--iO', action='store_false',help='Disable inputs as outputs')
  # Options to log additional information
  parser.add_argument('--log-enc', nargs=1, help='Save the generated encodings in the given directory')
  parser.add_argument('--log-spec', nargs=1, help='Log intermediate results')
  parser.add_argument('--log-iteration-steps', metavar='int-TIME',nargs=1, type=int, help="Time before logging of an intermediate result shall take place")
  parser.add_argument('--log-time-steps', metavar='int-ITERATIONS', nargs=1, type=int, help="Nof iterations before logging of an intermediate result shall take place")
  
  args = parser.parse_args()

  spec = args.specification
  limit = args.limit
  assert limit > 0, "The limit must be a positive number"
  config = Configuration()

  if args.gs :
    config.gate_size = args.gs[0]
  else :
    config.gate_size = 2

  if args.size :
    assert args.size[0] >= 2, "To reduce the size of a circuit, generally subcircuits with size of at least 2 must be considered."
    config.initial_subcircuit_size = args.size[0]
  else :
    config.initial_subcircuit_size = 6

  if args.aig :
    config.synthesiseAig = True
  else :
    if args.aig_out :
      parser.error('--aig is required when --aig-out is set.')
    config.synthesiseAig = False

  if args.seed :
    config.seed = args.seed[0]
  else :
    config.seed = None

  if args.syn_mode :
    if args.syn_mode == "qbf" :
      config.synthesis_approach = Configuration.SynthesisationMode.qbf
    elif args.syn_mode == "qbf-clausal" :
      config.synthesis_approach = Configuration.SynthesisationMode.qbf_clausal
    elif args.syn_mode == "equivalent" :
      config.synthesis_approach = Configuration.SynthesisationMode.exact
    else :
      assert False
  else :
    config.synthesis_approach = Configuration.SynthesisationMode.qbf

  if args.qbf_solver :
    if args.qbf_solver == 'qfun' :
      if config.synthesis_approach in {Configuration.SynthesisationMode.qbf_clausal, Configuration.SynthesisationMode.relation_qbf} :
        parser.error('QBF clausal encodings cannot be used with the qfun')
      config.qbf_solver = Configuration.QBFSolver.QFun
    elif args.qbf_solver == 'caqe' :
      if config.synthesis_approach in {Configuration.SynthesisationMode.qbf, Configuration.SynthesisationMode.exact} :
        parser.error('QBF circuit encodings cannot be used with the solvers caqe')
      config.qbf_solver = Configuration.QBFSolver.caqe
    elif args.qbf_solver == 'miniqu' :
      config.qbf_solver = Configuration.QBFSolver.miniQU
    elif args.qbf_solver == 'quabs' :
      if config.synthesis_approach in {Configuration.SynthesisationMode.qbf_clausal, Configuration.SynthesisationMode.relation_qbf} :
        parser.error('QBF clausal encodings cannot be used with the quabs')
      config.qbf_solver = Configuration.QBFSolver.quabs
    elif args.qbf_solver == 'qute' :
      if config.synthesis_approach in {Configuration.SynthesisationMode.qbf, Configuration.SynthesisationMode.exact} :
        parser.error('QBF circuit encodings cannot be used with the solvers qute')
      config.qbf_solver = Configuration.QBFSolver.qute
    else :
      assert False
  else :
    if config.synthesis_approach in {Configuration.SynthesisationMode.qbf, Configuration.SynthesisationMode.exact} :
      config.qbf_solver = Configuration.QBFSolver.QFun
    elif config.synthesis_approach in {Configuration.SynthesisationMode.qbf_clausal, Configuration.SynthesisationMode.relation_qbf} :
      config.qbf_solver = Configuration.QBFSolver.caqe

  if args.it :
    iteration_limit = args.it[0]
  else :
    iteration_limit = None

  ordered_specification = args.sorted
  if args.single_output :
    config.search_strategy = Configuration.SearchStrategy.SingleOutputSubcircuit
  config.use_dynamic_timeouts = args.dynTO

  if args.qbfTO :
    config.base_timeout = args.qbfTO[0]
  else :
    config.base_timeout = 120

  config.useTrivialRuleConstraint = args.N
  config.useAllStepsConstraint = args.A
  config.useNoReapplicationConstraint = args.R
  config.useOrderedStepsConstraint = args.O

  config.require_reduction = args.require_reduction
  config.allowConstantsAsOutputs = args.cO
  config.allowInputsAsOutputs = args.iO
  
  if not args.log_enc and not args.log_spec and (args.log_iteration_steps or args.log_time_steps) :
    parser.error('Log steps given but neither specifications nor encodings shall be logged')

  if args.log_enc :
    config.encoding_log_dir = args.log_enc[0]
  else :
    config.encoding_log_dir = None
  if args.log_spec :
    config.specification_log_dir = args.log_spec[0]
  else :
    config.specification_log_dir = None
  if args.log_iteration_steps :
    config.log_iteration_steps = args.log_iteration_steps[0]
  else :
    config.log_iteration_steps = None
  if args.log_time_steps :
    config.log_time_steps = args.log_time_steps[0]
  else :
    log_time_steps = None

  synthesiser = Synthesismanager(spec, config, ordered_specification)

  if args.restarts :
    config.runs = args.restarts[0] + 1

  if args.abc :
    config.use_abc = True
    if args.abc_cmds :
      config.abc_preprocess_cmds = args.abc_cmds[0]
      config.abc_cmds = args.abc_cmds[1]

  synthesiser.reduce((limit, iteration_limit))

  synthesiser.writeSpecification(args.synthesised_circuit)
  if args.aig and args.aig_out :
    aig_fname = args.aig_out[0]
    if not aig_fname.endswith(".aig") and not aig_fname.endswith(".aag") :
      aig_fname += ".aig"
    synthesiser.writeSpecification(aig_fname, False)


