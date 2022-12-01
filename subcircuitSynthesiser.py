from enum import Enum
import sys
import re
import subprocess
import time
import tempfile
import logging
import bitarray.util

from encoderCircuits import EncoderCircuits
from encoderCircuitsExact import EncoderExactSynthesis

import blifIO
import utils

from utils import miniQU_path
from utils import quabs_path
from utils import qfun_path


class TimeManager :
  def __init__(self, config : utils.Configuration) :
    # Logging
    self.total_time = 0
    self.totalised_time = 0
    self.solving_time = 0
    self.encoding_time = 0
    self.circuit_integration_time = 0
    self.logging_equivalent_replacements = 0

    self.timeout_per_nof_gates = {}
    self.recorded_timings_sat = {}
    self.recorded_timings_unsat = {}
    self.recorded_timeouts = {}

    # Timeout computation
    self.use_timeout = config.use_timeouts
    self.use_dynamic_timeouts = config.use_dynamic_timeouts
    self.required_timings = config.required_timings
    self.minimal_timeout = config.minimal_timeout
    self.base_timeout = config.base_timeout
    self.factor = config.factor
    # Adjust the mean until we recorded self.adjust_until timing 
    self.adjust_until = config.adjust_until


  def logSatTiming(self, size, time) :
    self.totalised_time += time
    self.solving_time += time
    if size in self.recorded_timings_sat :
      self.recorded_timings_sat[size].append(time)
    else :
      self.recorded_timings_sat[size] = [time]

  def logUnsatTiming(self, size, time) :
    self.totalised_time += time
    self.solving_time += time
    if size in self.recorded_timings_unsat :
      self.recorded_timings_unsat[size].append(time)
    else :
      self.recorded_timings_unsat[size] = [time]
    
  def logEncodingTime(self, time) :
    self.totalised_time += time
    self.encoding_time += time


  def logTimeout(self, size) :
    self.totalised_time += self.timeout_per_nof_gates[size]
    self.solving_time += self.timeout_per_nof_gates[size]
    if size in self.recorded_timeouts :
      self.recorded_timeouts[size] += 1
    else :
      self.recorded_timeouts[size] = 1

  def logIntegrationTime(self, time) :
    self.totalised_time += time
    self.circuit_integration_time += time


  def isTimeoutSet(self, size) :
    return size in self.timeout_per_nof_gates

  def initTimeout(self, size) :
    self.timeout_per_nof_gates[size] = self.base_timeout

  def useTimeout(self) :
    return self.use_timeout

  def getTimeout(self, size) :
    if size in self.timeout_per_nof_gates :
      return self.timeout_per_nof_gates[size]
    else :
      return self.base_timeout

  def getMeanSatTime(self, size) :
    assert size in self.recorded_timings_sat and len(self.recorded_timings_sat) > 0
    return utils.mean(self.recorded_timings_sat[size])

  def _getAdjustedMeanTime(self, val) :
    return (sum(val) + self.base_timeout) / (len(val) + 1)

  def _updateTimeouts(self, used_time, nof_gates) :
    self.logSatTiming(nof_gates, used_time)
    if not self.use_dynamic_timeouts :
      for i in range(nof_gates, -1, -1) :
        if not i in self.timeout_per_nof_gates :
          self.timeout_per_nof_gates[i] = self.base_timeout
      return
    if len(self.recorded_timings_sat[nof_gates]) > self.adjust_until :
      adjusted_mean = sum(self.recorded_timings_sat[nof_gates]) / len(self.recorded_timings_sat[nof_gates])
    else :
      adjusted_mean = self._getAdjustedMeanTime(self.recorded_timings_sat[nof_gates])
    if self.factor * adjusted_mean < self.base_timeout :
       base_time = self.factor * adjusted_mean
    else :
      base_time = self.base_timeout
    base_time = max(self.minimal_timeout, base_time)
    if nof_gates in self.timeout_per_nof_gates :
      self.timeout_per_nof_gates[nof_gates] = min(self.timeout_per_nof_gates[nof_gates], base_time)
    else :
      self.timeout_per_nof_gates[nof_gates] = base_time
    for i in range(nof_gates - 1, -1, -1) :
      if i in self.timeout_per_nof_gates :
        self.timeout_per_nof_gates[i] = min(self.timeout_per_nof_gates[i], base_time)
      else :
        self.timeout_per_nof_gates[i] = base_time

  def printLoggedTimings(self) :
    print(f"Time: {self.total_time}")
    print(f"Summed Component Timings {self.totalised_time}")
    print(f"Solving Time: {self.solving_time}")
    print(f"Encoding Time: {self.encoding_time}")
    print(f"Circuit Integration Time: {self.circuit_integration_time}")
    print(f"Time Logging Equivalent Replacements: {self.logging_equivalent_replacements}")

    self.printAverageSolverRuntimesPerCircuitSize()
    self.printAverageSATSolverRuntimesPerCircuitSize()
    self.printAverageUnsatSolverRuntimePerCircuitSize()
    self.printTimeouts()
    self.printNofRecordedTimeouts()

  def printAverageSolverRuntimesPerCircuitSize(self) :
    if len(self.recorded_timings_sat) == 0 :
      return
    max_checked_size = max(self.recorded_timings_sat.keys())
    for size in range(max_checked_size + 1) :
      nof_checks = 0
      total_time = 0
      if size in self.recorded_timings_sat :
        nof_checks += len(self.recorded_timings_sat[size])
        total_time += sum(self.recorded_timings_sat[size])
      if size in self.recorded_timings_unsat :
        nof_checks += len(self.recorded_timings_unsat[size])
        total_time += sum(self.recorded_timings_unsat[size])
      if nof_checks == 0 :
        continue
      print(f"Size: {size}; Nof checks: {nof_checks}; total time: {total_time}; average time: {total_time / nof_checks}")

  def printAverageSATSolverRuntimesPerCircuitSize(self) :
    checked_sizes = sorted(self.recorded_timings_sat.keys())
    for size in checked_sizes :
      timings = self.recorded_timings_sat[size]
      print(f"Size: {size}; Nof checks: {len(timings)}; total time: {sum(timings)}; average sat time: {utils.mean(timings)}")

  def printAverageUnsatSolverRuntimePerCircuitSize(self) :
    checked_sizes = sorted(self.recorded_timings_unsat.keys())
    for size in checked_sizes :
       timings = self.recorded_timings_unsat[size]
       print(f"Size: {size}; Nof checks: {len(timings)}; total time: {sum(timings)}; average unsat time: {utils.mean(timings)}")

  def printTimeouts(self) :
    sizes = sorted(self.timeout_per_nof_gates.keys())
    for x in sizes :
      print(f"Size: {x}; timeout: {self.timeout_per_nof_gates[x]}")

  def printNofRecordedTimeouts(self) :
    sizes = sorted(self.recorded_timeouts.keys())
    for x in sizes :
      print(f"Size: {x}; nof recorded timeouts: {self.recorded_timeouts[x]}")


class SubcircuitSynthesiser :


  def __init__(self, spec, config : utils.Configuration) :
    self.specification = spec
    self.config = config
    self.timer = TimeManager(config)

    self.nof_replacements_per_size = {}
    self.total_nof_checks_per_size = {}

    # check and log equivalences of replaced subcircuits
    self.subcir_equiv_dir = {}

    # Log the number of of checked subcircuits
    self.subcircuit_counter = 0



  def _logNofReplacements(self, to_replace, circuit, size) :
    if size in self.nof_replacements_per_size :
      self.nof_replacements_per_size[size] += 1
    else :
      self.nof_replacements_per_size[size] = 1
    if self.config.log_nof_equivalent_subcircuits :
      self.logEquivalentReplacement(to_replace, circuit, size)

  def reduce(self, to_replace, nof_gate_inputs, require_reduction) :
    start = time.time()
    if self.config.synthesis_approach == utils.Configuration.SynthesisationMode.qbf :
      assert self.config.qbf_solver in {utils.Configuration.QBFSolver.QFun, utils.Configuration.QBFSolver.quabs, utils.Configuration.QBFSolver.miniQU}, "Invalid qbf solver selected."
      realisable, size, circuit, timeout = self.synthesiseQBF(to_replace, nof_gate_inputs, require_reduction, self.timer)
    elif self.config.synthesis_approach == utils.Configuration.SynthesisationMode.exact :
      assert self.config.qbf_solver in {utils.Configuration.QBFSolver.QFun, utils.Configuration.QBFSolver.quabs, utils.Configuration.QBFSolver.miniQU}, "Invalid qbf solver selected."
      realisable, size, circuit, timeout = self.synthesiseExact(to_replace, nof_gate_inputs, require_reduction, self.timer)
    else :
      assert False
    self.timer.total_time += time.time() - start
    if realisable :
      self._logNofReplacements(to_replace, circuit, size)
      gates, output_association, subcircuit_inputs, gate_names = circuit
      unused = self.specification.replaceSubcircuit(to_replace, gates, output_association)
      return realisable, (gate_names, output_association, unused), False
    else :
      return realisable, None, timeout


  # supports only the QBF encoding
  def bottomUpReduction(self, to_replace, config) :
    nof_gate_inputs = self.config.gate_size
    use_input_vars = self.config.useGateInputVariables
    circuit_size = 1 if not self.config.allowInputsAsOutputs and not self.config.allowConstantsAsOutputs else 0
    encoder = EncoderCircuits(self.specification, to_replace, config)
    encoder.useGateInputVariables(use_input_vars)
    if len(encoder.getSubcircuitInputs()) < nof_gate_inputs :
      logging.warn(f"The given circuit must have at least {nof_gate_inputs} inputs")
      return -1
    self.use_timeout = False
    start = time.time()
    while True :
      current_realisable, subcir = self._checkEncoding(encoder, to_replace, circuit_size, nof_gate_inputs, self.timer)
      if current_realisable :
        break
      circuit_size += 1
    synthesis_time = time.time() - start
    logging.info(f"Synthesis time {synthesis_time}")
    gates, output_association, subcircuit_inputs, gate_names = subcir
    self.specification.replaceSubcircuit(to_replace, gates, output_association)
    return circuit_size


  def synthesiseQBF(self, to_replace, nof_gate_inputs, require_reduction, timer) :
    try :
      encoder = EncoderCircuits(self.specification, to_replace, self.config)
      encoder.useGateInputVariables(self.config.useGateInputVariables)
      if len(encoder.subcircuit_inputs) < nof_gate_inputs : # TODO: Find a cleaner solution
        return False, None, None, False
      return self.synthesise(encoder, to_replace, nof_gate_inputs, require_reduction, timer)
    except utils.NoOutputException :
      logging.warning("Subcrcuit with no outputs detected")
      print(f"To replace: {to_replace}")
      return True, ([], {}, []), False



  def synthesiseExact(self, to_replace, nof_gate_inputs, require_reduction, timer) :
    try :
      encoder = self._setupEquivEncoder(to_replace)
      if len(encoder.inputs) < nof_gate_inputs : # TODO: Find a cleaner solution
        return False, None, None, False
      return self.synthesise(encoder, to_replace, nof_gate_inputs, require_reduction, timer)
    except utils.NoOutputException :
      logging.warning("Subcrcuit with no outputs detected")
      print(f"To replace: {to_replace}")
      return True, ([], {}, []), False



  def _incrementCheckCounter(self, nof_gates) :
    if nof_gates in self.total_nof_checks_per_size :
      self.total_nof_checks_per_size[nof_gates] += 1
    else :
      self.total_nof_checks_per_size[nof_gates] = 1

  def logEquivalentReplacement(self, to_replace, new_subcircuit, size) :
    start = time.time()
    if self.isEquivalentReplacement(to_replace, new_subcircuit) :
      if size in self.subcir_equiv_dir :
        self.subcir_equiv_dir[size] += 1
      else :
        self.subcir_equiv_dir[size] = 1
    self.timer.logging_equivalent_replacements += time.time() - start

  def isEquivalentReplacement(self, to_replace, new_subcircuit) :
    subcircuit_inputs = list(self.specification.getSubcircuitInputs(to_replace))
    subcircuit_outputs = list(self.specification.getSubcircuitOutputs(to_replace))
    current_subcirc_io = (subcircuit_inputs, subcircuit_outputs)
    old_gates = [(g.getAlias(), g.inputs, g.table) for g in self.specification.orderedGateTraversal() if g.getAlias() in to_replace]
    old_subcir = current_subcirc_io + tuple([old_gates])
    gates, output_association, _, _ = new_subcircuit
    new_outputs = [output_association[x] for x in subcircuit_outputs]
    new_subcir = (subcircuit_inputs, new_outputs, gates)
    return utils.checkSubcircuitsForEquivalence(old_subcir, new_subcir)

  def analyseOriginalSize(self, encoder, to_replace, nof_gate_inputs, timer, clausal_encoding = False) :
    nof_gates = len(to_replace)
    try :
      realisable, subcir_candidate = self._checkEncoding(encoder, to_replace, nof_gates, nof_gate_inputs, timer, clausal_encoding)
      if not realisable :
        if self.config.symmetryBreakingUsed() :
          encoder.disableSymmetryBreaking()
          realisable, subcir_candidate = self._checkEncoding(encoder, to_replace, nof_gates, nof_gate_inputs, timer, clausal_encoding)
        if not realisable :
          logging.warning("Warning: Cannot be replaced by circuit of initial size")
          print(f"to_replace: {to_replace}")
          return False, None
        else :
          logging.info("Information: Symmetry breaking constraints prevented realisation")
    except subprocess.TimeoutExpired as e :
      timer.logTimeout(nof_gates)
      return False, None
    return realisable, subcir_candidate

  def synthesise(self, encoder, to_replace, nof_gate_inputs, require_reduction, timer, clausal_encoding = False) :
    self.subcircuit_counter += 1
    realisable = False
    max_size = len(to_replace) - 1 if require_reduction else len(to_replace)
    if not timer.isTimeoutSet(max_size) :
      timer.initTimeout(max_size)
    if not require_reduction :
      realisable, subcir_candidate = self.analyseOriginalSize(encoder, to_replace, nof_gate_inputs, timer, clausal_encoding)
      if not realisable :
        return realisable, None, None, False
      smallest_representation = len(to_replace)
    bound = len(to_replace) - 1
    for nof_gates in range(bound, 0, -1) :
      try :
        self._incrementCheckCounter(nof_gates)
        current_realisable, subcir = self._checkEncoding(encoder, to_replace, nof_gates, nof_gate_inputs, timer, clausal_encoding)
        if current_realisable :
          realisable = True
          smallest_representation = nof_gates
          subcir_candidate = subcir
        else :
          break
      except subprocess.TimeoutExpired as e :
        timer.logTimeout(nof_gates)
        if not realisable : # used if require_reduction is True
          return False, None, None, True
        else :
          break
    
    if self.config.allowInputsAsOutputs or self.config.allowConstantsAsOutputs :
      try :
        self._incrementCheckCounter(0)
        current_realisable, subcir = self._checkEncoding(encoder, to_replace, 0, nof_gate_inputs, timer, clausal_encoding)
        if current_realisable :
          realisable = True
          smallest_representation = 0
          subcir_candidate = subcir
      except subprocess.TimeoutExpired as e :
        logging.debug("Timeout: check for size 0")
      
    if not realisable :
      return realisable, None, None, False

    if self.config.log_replaced_gates :
      gates, output_association, subcircuit_inputs, gate_names = subcir_candidate
      print(f"Replaced: gates: {to_replace}")
      print(f"New gates: {gate_names}")
      print(f"Output association: {output_association}")

    return realisable, smallest_representation, subcir_candidate, False


  def printLoggedTimings(self) :
    self.timer.printLoggedTimings()

  def printReplacementCounts(self) :
    sizes = sorted(self.nof_replacements_per_size)
    for x in sizes :
      nof_replacments = self.nof_replacements_per_size[x]
      if self.config.log_nof_equivalent_subcircuits :
        nof_equiv_replacements = 0
        if x in self.subcir_equiv_dir :
          nof_equiv_replacements = self.subcir_equiv_dir[x]
        print(f"Size: {x}; replacements {nof_replacments}; equivalent replacements {nof_equiv_replacements}")
      else :
        print(f"Size: {x}; replacements {nof_replacments}")

  def _getSubcircuitInformations(self, to_replace) :
    input_set = self.specification.getSubcircuitInputs(to_replace)
    output_set = self.specification.getSubcircuitOutputs(to_replace)
    return (input_set, output_set)

  def _setupEquivEncoder(self, to_replace) :
    input_set = set()
    outputs = []
    gates = []
    to_replace_set = set(to_replace)
    gate_variables = set()
    pos_set = set(self.specification.getOutputs())
    for gate in self.specification.orderedGateTraversal() :
      if gate.getAlias() in to_replace_set : 
        anded, lines = gate.getQCIRGates()        
        gates.append((gate.getAlias(), anded, lines))
        input_set.update(gate.inputs)
        gate_outputs = self.specification.getGateOutputs(gate.getAlias())
        if not to_replace_set.issuperset(gate_outputs) or gate.getAlias() in pos_set :
          outputs.append(gate.getAlias())
        gate_variables.add(gate.getAlias())
    inputs = [x for x in input_set if not x in to_replace]

    potential_cycles = self.specification.getPotentialCycles(inputs, outputs, gate_variables)
    encoder = EncoderExactSynthesis(inputs, outputs, gates, potential_cycles, self.config)
    return encoder

  def _writeEncoding(self, file, encoder, nof_gates, nof_gate_inputs) :
    start = time.time()
    encoder.getEncoding(nof_gates, nof_gate_inputs, file)
    return time.time() - start

  def _checkEncoding(self, encoder, to_replace, nof_gates, nof_gate_inputs, timer, clausal_encoding = False) :
    timeout = 0
    if timer.useTimeout() :
      timeout = timer.getTimeout(nof_gates)
    encoding_suffix = ".qdimacs" if clausal_encoding else ".qcir"
    if self.config.encoding_log_dir is not None :
      fname = self.config.encoding_log_dir + "/iteration_" + str(self.subcircuit_counter) + "_nofGates_" + str(nof_gates) + encoding_suffix
      with open(fname,"w") as out: 
        encoding_time = self._writeEncoding(out, encoder, nof_gates, nof_gate_inputs)
      realisable, assignment, used_time, valid = self._runSolverAndGetAssignment(fname, timeout)
    else :
      with tempfile.NamedTemporaryFile(mode = "w", suffix = encoding_suffix, delete=True) as tmp:
        encoding_time = self._writeEncoding(tmp, encoder, nof_gates, nof_gate_inputs)
        tmp.flush()
        realisable, assignment, used_time, valid = self._runSolverAndGetAssignment(tmp.name, timeout)
    timer.logEncodingTime(encoding_time)
    if not valid :
      logging.critical("QBF yielded invalid resuls -- error in encoding")
      self._logError(encoder, to_replace, len(to_replace), nof_gate_inputs)
      assert False
    if realisable :
      if timer.useTimeout() :
        timer._updateTimeouts(used_time, nof_gates)
      else :
        timer.logSatTiming(nof_gates, used_time)
      subcircuit_data = self._extractGatesFromAssignment(to_replace, encoder, nof_gates, nof_gate_inputs, assignment)
      return realisable, subcircuit_data
    else :
      timer.logUnsatTiming(nof_gates, used_time)
      return realisable, None

  def _extractGatesFromAssignment(self, to_replace, encoder, nof_gates, nof_gate_inputs, assignment) :
    if nof_gates <= len(to_replace) :
      gate_names = to_replace[:nof_gates]
    else :
      gate_names = to_replace + [self.specification.max_var + i + 1 for i in range(nof_gates - len(to_replace))]

    gate_definition_variables = encoder.getGateDefinitionVariables()
    selection_variables = encoder.getSelectionVariables()
    gate_output_variables = encoder.getGateOutputVariables()
    subcircuit_inputs = encoder.getSubcircuitInputs()
    subcircuit_outputs = encoder.getSubcircuitOutputs()

    gates = []
    output_association = {} # associates the outputs of the subcircuits with replaced gates
    for i in range(nof_gates) :
      inputs = []
      for j, s in enumerate(selection_variables[i]) :
        if assignment[s] == 1:
          if j < len(subcircuit_inputs) :
            inputs += [subcircuit_inputs[j]]
          else :
            inputs += [gate_names[j - len(subcircuit_inputs)]]
      
      gate_definitions = bitarray.util.zeros(2 ** nof_gate_inputs)
      offset = 1 # We use normal gates
      for j in range(offset, 2 ** nof_gate_inputs) :
        if assignment[gate_definition_variables[i][j - offset]] == 1:
          gate_definitions[j] = 1

      gates += [(gate_names[i], inputs, gate_definitions)]

      for j, o in enumerate(gate_output_variables[i]) :
        if assignment[o] == 1:
          output_association[subcircuit_outputs[j]] = gate_names[i]

    allow_inputs_as_outputs = self.config.allowInputsAsOutputs
    allow_constants_as_outputs = self.config.allowConstantsAsOutputs

    if allow_inputs_as_outputs :
      for i in range(nof_gates, nof_gates + len(subcircuit_inputs)) :
        for j, o in enumerate(gate_output_variables[i]) :
          if assignment[o] == 1:
            output_association[subcircuit_outputs[j]] = subcircuit_inputs[i - nof_gates]

    if allow_constants_as_outputs :
      for j, o in enumerate(gate_output_variables[-1]) : 
        if assignment[o] == 1:
          output_association[subcircuit_outputs[j]] = None # If the output is a constant the output is associated to no gate

    return (gates, output_association, subcircuit_inputs, gate_names)


  def _runSolverAndGetAssignment(self, input, timeout=0) :
    if self.config.qbf_solver == utils.Configuration.QBFSolver.miniQU :
      solver_cmd = [miniQU_path, "-cert", input]
      output_pattern = r"\nV\s*(.*)\s*\n"
    elif self.config.qbf_solver == utils.Configuration.QBFSolver.quabs :
      solver_cmd = [quabs_path, "--partial-assignment", input]
      output_pattern = r"\nV\s*(.*)\s*r"
    elif self.config.qbf_solver == utils.Configuration.QBFSolver.QFun :
      solver_cmd = [qfun_path, input]
      output_pattern = r"\nv\s*(.*)\n*"
    else :
      assert False

    start = time.time()
    result = subprocess.run(solver_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout = timeout if timeout != 0 else None)
    solving_time = time.time() - start
    if result.returncode == 10:
      solver_output = result.stdout.decode("utf-8")
      assignment = self._getAssignment(solver_output, output_pattern)
      return True, assignment, solving_time, True
    elif result.returncode == 20:
      return False, [], solving_time, True
    else :
      print("Solver message:", file=sys.stderr)
      print(result.stdout, file=sys.stderr)
      print(result.stderr, file=sys.stderr)
      return False, [], 0, False


  def _getAssignment(self, output, output_pattern) :
    st=re.search(output_pattern, output)
    assert not st is None
    assignment = {}
    assignment_str=st.groups()[0]
    for l in assignment_str.split() :
      lit = int(l)
      if lit == 0 :
        continue
      assignment[abs(lit)] = lit > 0
    return assignment


  def _logError(self, encoder, to_replace, nof_gates, nof_gate_inputs) :
    print("************ Error Log ************", file=sys.stderr)
    print(f"Root gate: {to_replace[0]}", file=sys.stderr)
    subcir_gates = " ".join(str(x) for x in to_replace)
    print(f"Subcircuit gates: {subcir_gates}", file=sys.stderr)
    print("===================================", file=sys.stderr)
    print("Specification:", file=sys.stderr)
    print("===================================", file=sys.stderr)
    blifIO.writeSpecification2Stream(sys.stderr, self.specification, "Error")
    print("", file=sys.stderr)
    print("===================================", file=sys.stderr)
    print("Encoding:", file=sys.stderr)
    print("===================================", file=sys.stderr)
    encoder.getEncoding(nof_gates, nof_gate_inputs, sys.stderr)