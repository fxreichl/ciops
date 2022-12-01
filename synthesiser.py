
import random
import time
import logging


from subcircuitSynthesiser import SubcircuitSynthesiser
from utils import Configuration
from utils import mean


import aigerIO
import blifIO


class Synthesiser :
      

  @staticmethod
  def getSpecification(spec, ordered_inputs = False) :
    if spec.endswith(".aig") or spec.endswith(".aag") :
      return aigerIO.getSpecification(spec)
    else :
      assert spec.endswith(".blif")
      return blifIO.getSpecification(spec, ordered_inputs)

  @staticmethod
  def getSynthesiser(spec, config, ordered_inputs = False) :
    specification = Synthesiser.getSpecification(spec, ordered_inputs)
    return Synthesiser(specification, config)
    

  def __init__(self, spec, config : Configuration) :
    self.specification = spec
    config.validateConfig()
    self.config = config
    self.synthesiser = SubcircuitSynthesiser(self.specification, config)
    
    # If the QBF calls yielding SAT are very fast increase the size of the considered subcircuits
    self.subcircuit_size_validated = False
    self.check_for_larger_subcircuits = True
    self.last_validated = None
    self.time_subcircuit_selection = 0

    # Map a gate to the iteration counter, where it was analysed
    # A dictionary preserves the insertion order
    self.taboo_dict = {} 

    self.replacements_single_output_subcircuits = 0
    self.reduction_single_output_subcircuits = 0
    self.replacements_multi_output_subcircuits = 0
    self.reduction_multi_output_subcircuits = 0

  def _getEllapsedTime(self) :
    return time.time() - self.start

  def _checkTime(self) :
    x = self._getEllapsedTime()
    if x > self.total_available_time :
      return False
    else:
       return True

  def reduce(self, budget, subcircuit_size, nof_inputs) :
    available_time, available_iterations = budget
    self.total_available_time = available_time
    self.start = time.time()
    self._traverseGates(available_iterations, subcircuit_size, nof_inputs)
    return self

  def printStatistics(self) :
    print("*************************************************")
    print(f"Combined synthesis time:                {self._getEllapsedTime()}")
    print(f"Time subcircuit selection: {self.time_subcircuit_selection}")
    self.synthesiser.printLoggedTimings()
    self.synthesiser.printReplacementCounts()
    print(f"Single output subcircuits: replacements: {self.replacements_single_output_subcircuits}; reductions: {self.reduction_single_output_subcircuits}")
    print(f"Multiple output subcircuits: replacements: {self.replacements_multi_output_subcircuits}; reductions: {self.reduction_multi_output_subcircuits}")
    print("*************************************************")
    
  def _traverseGates(self, budget, subcircuit_size, nof_inputs) :
    if self.specification.getNofGates() < nof_inputs :
      return
    self._randomTraversal(budget, subcircuit_size, nof_inputs)

  def _getRandomGate(self) :
    gates = self.specification.getGateAliasesSet()
    gate_var_list = sorted(gates.difference(self.taboo_dict)) 
    if len(gate_var_list) == 0 :
      return None
    rv = random.randint(0, len(gate_var_list) - 1)
    root_gate = gate_var_list[rv]
    return root_gate


  def _replaceSubcircuit(self, to_replace, nof_inputs) :
      if self.config.require_reduction and not self.subcircuit_size_validated :
        # If we do not require a reduction we know that we will obtain an encoding that is SAT.
        # Based on the time that is needed to solve this encoding we set the timeout
        return self.synthesiser.reduce(to_replace, nof_inputs, False)
      else :
        return self.synthesiser.reduce(to_replace, nof_inputs, self.config.require_reduction)



  def _randomTraversal(self, budget, subcircuit_size, nof_inputs) :
    check_budget = budget is not None
    log_spec_time_steps = self.config.log_time_steps is not None and self.config.specification_log_dir is not None
    log_spec_iteration_steps = self.config.log_iteration_steps is not None and self.config.specification_log_dir is not None
    counter = 0
    intermediate_counter = 0
    while True :
      if check_budget and counter >= budget :
        logging.info(f"Available iterations used up. Nof considered subcircuits: {counter}")
        return
      if not self._checkTime() :
        logging.info(f"Available time used up. Nof considered subcircuits: {counter}")
        return
      start = time.time()
      counter += 1

      # ignore subcircuits of length 1
      subcircuit_search_counter = 0
      while True :
        subcircuit_search_counter += 1
        root_gate = self._getRandomGate()
        if root_gate is None :
          logging.info("Too many subcircuits of size 1 -- it is unlikely to reduce the circuit")
          return
        to_replace = self._getSubcircuitGates(root_gate, subcircuit_size)
        if len(to_replace) == 1 :
          self.taboo_dict[root_gate] = counter
        else :
          break
        
      self.time_subcircuit_selection += (time.time() - start)

      replaceable, subcir_data, timeout = self._replaceSubcircuit(to_replace, nof_inputs)
      logging.debug(f"iteration: {counter}; root gate: {root_gate}; old-size: {len(to_replace)}; new-size: {len(subcir_data[0]) if replaceable  else '-'}; to replace: {to_replace}")

      if not self.subcircuit_size_validated :
        if timeout :
          if self.last_validated is None :
            subcircuit_size -= 1
            if subcircuit_size < 2 :
              logging.warn("The encoding for a subcircuit with 2 gates could not be solved by the QBF solver within the given timeout.")
              logging.warn("Restart with a longer timeout -- be aware if the given timeout was already reasonably long then maybe the specification is too hard.")
              return
          else :
            subcircuit_size = self.last_validated
            self.subcircuit_size_validated = True
          self.check_for_larger_subcircuits = False
          logging.info(f"QBF call takes too long -- decrease the subcircuit size to: {subcircuit_size}")
        elif replaceable and subcircuit_size == len(to_replace) :
          self.subcircuit_size_validated = True
          self.last_validated = subcircuit_size
      
      if self.check_for_larger_subcircuits and counter % self.config.check_subcircuit_size_interval == 0 :
        if subcircuit_size in self.synthesiser.timer.recorded_timings_sat and len(self.synthesiser.timer.recorded_timings_sat[subcircuit_size]) > self.config.subcircuit_size_increase_nof_samples :
          if mean(self.synthesiser.timer.recorded_timings_sat[subcircuit_size]) < self.config.subcircuit_size_increase_limit :
            subcircuit_size += 1
            self.subcircuit_size_validated = False
            logging.info(f"QBF call fast -- increase the subcircuit size to {subcircuit_size}")

      if replaceable :
        gate_names, output_assoc, unused = subcir_data
        reduced = len(gate_names) < len(to_replace)

        if len(output_assoc) == 1 :
          self.replacements_single_output_subcircuits += 1
          if reduced :
            self.reduction_single_output_subcircuits += 1
        else :
          self.replacements_multi_output_subcircuits += 1
          if reduced :
            self.reduction_multi_output_subcircuits += 1

        if reduced :
          for g in to_replace :
            self.taboo_dict.pop(g, None)

        for g in to_replace :
          self.taboo_dict.pop(g, None)
        for g in unused :
          self.taboo_dict.pop(g, None)
        

        if self.specification.getNofGates() == 0 :
          logging.info("No Gates left.")
          return

        if self.config.use_taboo_list :
          if not root_gate in output_assoc :
            logging.warning(f"Root gate not in output association. root: {root_gate}, replace: {to_replace}, assoc: {output_assoc}")
          else :
            root_representation = output_assoc[root_gate]
            self.taboo_dict[root_representation] = counter

        if (log_spec_time_steps and int(self._getEllapsedTime() // self.config.log_time_steps) > intermediate_counter) :
          fname = f"{self.config.specification_log_dir}/spec_it_{counter}.blif"
          self.writeSpecification(fname)
          logging.info(f"Intermediate Results: {int(self._getEllapsedTime() // self.config.log_time_steps)} {self._getEllapsedTime()}")
          intermediate_counter += 1
        # Log intermediate results
        elif log_spec_iteration_steps and counter % self.config.log_iteration_steps == 0 :
          fname = f"{self.config.specification_log_dir}/spec_it_{counter}.blif"
          self.writeSpecification(fname)

      if self.config.use_taboo_list :
        self.taboo_dict[root_gate] = counter

        last_gate, last_counter = next(iter(self.taboo_dict.items()))
        while len(self.taboo_dict) > 0 and len(self.taboo_dict) >= self.config.taboo_ratio * self.specification.getNofGates() :
          self.taboo_dict.pop(last_gate, None)
          if len(self.taboo_dict) > 0 :
            last_gate, last_counter = next(iter(self.taboo_dict.items()))
          
      logging.debug(f"Iteration: {counter}; Nof Gates: {self.specification.getNofGates()}")


  # root_gate_var shall be the first element of the returned list
  def _getSubcircuitGates(self, root_gate_var, size) :
    if self.config.search_strategy == Configuration.SearchStrategy.OutputReduction :
      return self._OutputReduction(root_gate_var, size)
    elif self.config.search_strategy == Configuration.SearchStrategy.SingleOutputSubcircuit :
      return self._singleOutputExpansion(root_gate_var, size)
    else :
      assert False


  # Try to find a subcircuit with few outputs / inputs
  def _OutputReduction(self, root_gate_var, size) :
    selected_gates = set()
    potential_successors = {root_gate_var}
    current_output_set = set()
    while len(potential_successors) > 0 and len(selected_gates) < size :
      it = iter(potential_successors)
      best_gate = next(it)
      outputs = [x for x in self.specification.getGateOutputs(best_gate) if not x in selected_gates] #POs need to be considered
      best_nof_outputs = len(outputs)
      if best_gate in self.specification.getOutputs() :
        best_nof_outputs += 1
      best_nof_inputs = len([x for x in self.specification.getGateInputs(best_gate) if not x in selected_gates])
      best_level = self.specification.getGateLevel(best_gate)
      for gate in it :
        gate_outputs = [x for x in self.specification.getGateOutputs(gate) if not x in selected_gates]
        nof_outputs = len(gate_outputs)
        nof_inputs = len([x for x in self.specification.getGateInputs(gate) if not x in selected_gates])
        level = self.specification.getGateLevel(gate)
        if gate in self.specification.getOutputs() :
          nof_outputs += 1
        if gate in current_output_set :
          nof_outputs -= 1
        if nof_outputs < best_nof_outputs :
          best_gate = gate
          best_nof_inputs = nof_inputs
          best_nof_outputs = nof_outputs
          outputs = gate_outputs
          best_level = level
        elif nof_outputs == best_nof_outputs :
          nof_inputs = len([x for x in self.specification.getGateInputs(gate) if not x in selected_gates])
          if nof_inputs < best_nof_inputs :
            best_gate = gate
            best_nof_inputs = nof_inputs
            best_nof_outputs = nof_outputs
            outputs = gate_outputs
            best_level = level
          elif nof_inputs == best_nof_inputs and level < best_level :
            best_gate = gate
            best_nof_inputs = nof_inputs
            best_nof_outputs = nof_outputs
            outputs = gate_outputs
            best_level = level
      selected_gates.add(best_gate)
      potential_successors.remove(best_gate)
      current_output_set.update(outputs)
      potential_successors.update(set(x for x in self.specification.getGateInputs(best_gate) if not x in self.specification.getInputs() and not x in selected_gates))
    # The root gate shall be the first element of the list
    selected_gates.remove(root_gate_var)
    return [root_gate_var] + list(selected_gates)


  def _singleOutputExpansion(self, root_gate_var, size) :
    selected_gates = {root_gate_var}
    potential_successors = set(x for x in self.specification.getGateInputs(root_gate_var) if not x in self.specification.getInputs())
    found_gate = True
    while len(potential_successors) > 0 and len(selected_gates) < size and found_gate:
      for current_gate in potential_successors :
        found_gate = False
        gate_outputs = self.specification.getGateOutputs(current_gate)
        if selected_gates.issuperset(gate_outputs) :
          found_gate = True
          selected_gates.add(current_gate)
          potential_successors.discard(current_gate)
          potential_successors.update(x for x in self.specification.getGateInputs(current_gate) if not x in self.specification.getInputs() and not x in selected_gates)
          break
    selected_gates.discard(root_gate_var)
    return [root_gate_var] + list(selected_gates)