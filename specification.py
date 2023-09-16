import time
import sys
import logging

import bitarray
import bitarray.util

from utils import isNormalised
from utils import getBitSeq
from utils import getAllIndices

class Gate :
  
  def __init__(self, gate_alias, inputs, table) :
    self.gate_alias = gate_alias
    self.inputs = inputs
    self.table = table

  # renaming[x] = None indicates that x is a constant (false) gate
  def substitute(self, renaming) :
    removed = [idx for idx, x in enumerate(self.inputs) if x in renaming and renaming[x] is None]
    # Even if the gate is reduced to the constant gate we new the renamed inputs to update the gate outputs
    renamed_inputs = [renaming[x] if x in renaming else x for x in self.inputs if not x in renaming or not renaming[x] is None]
    if len(removed) > 0 :
      self._reduceTable(removed)
    if len(self.inputs) > 0 : 
      self.inputs = renamed_inputs
    return renamed_inputs

  def _reduceTable(self, to_remove) :
    for idx in to_remove :
      reversed_idx = len(self.inputs) - 1 - idx
      self.table = bitarray.bitarray(x for idx, x in enumerate(self.table) if idx % (2 ** (reversed_idx + 1)) < (2 ** (reversed_idx)))
    if not self.table.any() : # the table representing the constant false
      self.inputs = []
      self.table = bitarray.util.zeros(1)

  def isConstant(self) :
    return len(self.inputs) == 0

  # If the gate is a projection to one of its inputs, the index of the respective input is returned
  # Only apply if the gate is not constant
  # If gates can have more than two inputs: Only sufficient but not a necessary condition
  def projectionOn(self) :
    # A normal gate with one inputs represents either the constant false or the projection to its inputs
    if len(self.inputs) == 1 :
      return 0
    return None


  def getAlias(self) :
    return self.gate_alias

  # names: use the given inputs instead of self.inputs
  def getQCIRGates(self, names = None) :
    assert names is None or len(names) == len(self.inputs)
    input_names = self.inputs if names is None else names
    # If the gate is false for the majority of the input combinations we
    # represent the gate by a disjunction of conjunctions, otherwise by
    # a conjunction of disjunctions.
    anded = len([x for x in self.table if x > 0]) <= (2 ** (len(self.inputs) - 1))
    val = 1 if anded else 0
    lines = []
    for idx, tt_val in enumerate(self.table) :
      if tt_val == val :
        line = [input_names[i] if v == val else -input_names[i] for i,v in enumerate(getBitSeq(idx, len(self.inputs)))]
        lines.append(line)
    return (anded, lines)

  # names: use the given inputs instead of self.inputs
  def traverseTable(self, names = None) :
    assert names is None or len(names) == len(self.inputs)
    input_names = self.inputs if names is None else names
    for idx, tt_val in enumerate(self.table) : 
      inputs = [input_names[i] if v == 1 else -input_names[i] for i,v in enumerate(getBitSeq(idx, len(self.inputs)))]
      yield (inputs, tt_val)

class Specification :

  def __init__(self, pis, pos) :

    self.pis = pis
    self.pos = pos
    self.pos_set = set(self.pos)
    self.max_var = max(pis) # non pi outputs need to be introduced later
    # As we use bitarray anywhere we can replace the boolean array
    self.negated_pos = bitarray.util.zeros(len(pos))

    self.constant_gate_alias = None

    # Map the gate aliases to tuples (level, outputs, gate) 
    self.alias2gate = {}
    self.alias2outputs = {x : set() for x in self.pis}
    self.alias2level = {x : 0 for x in self.pis}

    self.topological_order = None

  def orderedGateTraversal(self) :
    # The constant gate is in alias2gate
    # if not self.constant_gate_alias is None :
    #   yield self.alias2gate[self.constant_gate_alias]
    for x in self.topological_order :
      yield self.alias2gate[x]

  def gateTraversal(self) :
    # The constant gate is in alias2gate
    # if not self.constant_gate_alias is None :
    #   yield self.alias2gate[self.constant_gate_alias]
    for _, gate in self.alias2gate.items() :
      yield gate

  def getGateAliases(self) :
    return list(self.alias2gate.keys())

  def getGateAliasesSet(self) :
    return set(self.alias2gate.keys())

  def getNofGates(self) :
    return len(self.alias2gate)

  def getGate(self, alias) :
    return self.alias2gate[alias]

  def getGateInputs(self, alias) :
    return self.alias2gate[alias].inputs

  def getGateOutputs(self, alias) :
    return self.alias2outputs[alias]

  def getGateLevel(self, alias) :
    return self.alias2level[alias]

  def getInputs(self) :
    return self.pis

  def getOutputs(self) :
    return self.pos

  def getMaxAlias(self) :
    return self.max_var

  def isOutputNegated(self, idx) :
    return self.negated_pos[idx]

  def isPO(self, alias) :
    return alias in self.pos_set

  def getDepth(self) :
    return max(self.alias2level[x] for x in self.pos)

  def getSubcircuitInputs(self, aliases) :
    input_set = set(x for y in aliases for x in self.getGateInputs(y))
    input_set.difference_update(aliases)
    return input_set

  def getDirectSuccessors(self, aliases) :
    successor_set = set(x for y in aliases for x in self.getGateOutputs(y))
    successor_set.difference_update(aliases)
    return successor_set

  def getSubcircuitOutputs(self, aliases) :
    alias_set = set(aliases)
    output_set = set(x for x in aliases if self.isPO(x) or not self.getGateOutputs(x).issubset(alias_set))
    return output_set

  def _getConnected(self, alias, gates, internal_gates) :
    level = min(self.alias2level[x] for x in gates)
    connected_pairs = []
    # The level of each element of gates is larger then the level of gates_var, thus there cannot be a connected pair
    if level >= self.alias2level[alias] :
      return connected_pairs
    to_check = [alias]
    seen = set(internal_gates) # internal gates shall be ignored. We are only interested in paths outside of the subcircuit.
    while len(to_check) > 0:
      current_gate = to_check.pop()
      seen.add(current_gate)
      for inp in self.getGateInputs(current_gate) :
        if inp in gates :
          connected_pairs.append((inp, alias))
        elif not inp in seen :
          seen.add(inp)
          inp_level = self.alias2level[inp]
          if inp_level > level :
            to_check.append(inp)
    return connected_pairs

  # computes a list of pairs whose first element is an output and whose second element is an input.
  # if the list contains a pair (a,b) then the input b depends on the output a
  def getPotentialCycles(self, inputs, outputs, internal_gates) :
    cycle_candidates = []
    if len(inputs) == 0 :
      logging.warning(f"Warning -- getPotentialCycles: inputs empty")
    if len(outputs) == 0 :
      logging.warning(f"Warning -- getPotentialCycles: outputs empty")
      return cycle_candidates
    for inp in inputs :
      cycle_candidates += self._getConnected(inp, outputs, internal_gates)
    return cycle_candidates

  def removeGate(self, alias) :
    self.removeGateAux(alias, self.getGateInputs(alias))

  # If we rename inputs, it is possible that inputs are removed.
  # But we want to process all old inputs
  def removeGateAux(self, alias, inputs) :
    assert alias in self.alias2gate
    for x in inputs :
      if x in self.alias2outputs : # if the input was already removed, it is not part of the dict
        self.alias2outputs[x].discard(alias)
    del self.alias2gate[alias]
    del self.alias2level[alias]
    del self.alias2outputs[alias]

  def insertGates(self, new_gates) :
    # To avoid errors if new_gates are not topologically ordered
    self.alias2outputs.update({x[0] : set() for x in new_gates})
    for g in new_gates :
      alias, inputs, table = g
      self.addGate(alias, inputs, table)


  def updatePos(self, output_assoc) :
    self.pos = [(self.getConstantAlias(x) if output_assoc[x] is None else output_assoc[x]) if x in output_assoc else x for x in self.pos]
    self.pos_set = set(self.pos)


  # As in a normalised circuit there is only one possibility for a constant gate
  # We only use a single representation
  def getConstantAlias(self, candidate) :
    if self.constant_gate_alias is None :
      self.constant_gate_alias = candidate
      self.alias2level[candidate] = 0
      self.alias2outputs[candidate] = set()
      gate = Gate(candidate, [], bitarray.util.zeros(1))
      self.alias2gate[candidate] = gate
    return self.constant_gate_alias

  def removeUnusedGates(self, aliases_to_check) :
    unused = set()
    while len(aliases_to_check) > 0 :
      x = aliases_to_check.pop()
      if not self.isPO(x) and len(self.getGateOutputs(x)) == 0 : # the gate is not used
        aliases_to_check.update(self.getGateInputs(x))
        aliases_to_check.difference_update(self.pis)
        self.removeGate(x)
        unused.add(x)
    return unused

  def getOutputsDict(self, to_remove, output_assoc) :
    subcircuit_outputs = self.getSubcircuitOutputs(to_remove)
    to_remove_set = set(to_remove)
    log = {}
    for x in subcircuit_outputs :
      outputs = self.getGateOutputs(x)
      outputs.difference_update(to_remove_set)
      # The constant gate is substituted. We only use the constant gate to represent constant pos.
      if output_assoc[x] is None :
        continue
      if output_assoc[x] in log :
        log[output_assoc[x]].update(outputs)
      else :
        log[output_assoc[x]] = outputs
    return log

  def incorportateOutputs(self, output_log) :
    for alias, outputs in output_log.items() :
      self.alias2outputs[alias].update(outputs)

  def replaceSubcircuit(self, to_remove, new_gates, output_assoc) :
    old_gate_aliases = set(x for x in to_remove)
    successors_to_update = self.getDirectSuccessors(old_gate_aliases)
    unused_gate_candidates = self.getSubcircuitInputs(old_gate_aliases)
    subcircuit_output_dict = self.getOutputsDict(to_remove, output_assoc)
    redundant = set()
    for x in to_remove :
      self.removeGate(x)
    self.insertGates(new_gates)
    self.incorportateOutputs(subcircuit_output_dict)
    while len(successors_to_update) > 0 :
      alias_to_process = successors_to_update.pop()
      gate = self.getGate(alias_to_process)
      old_inputs = gate.substitute(output_assoc)
      if gate.isConstant() :
        output_assoc[alias_to_process] = None
        successors_to_update.update(self.getGateOutputs(alias_to_process))
        redundant.add(alias_to_process)
        self.removeGateAux(alias_to_process, old_inputs)
        unused_gate_candidates.update(old_inputs)

    unused_gate_candidates.difference_update(self.pis)
    unused = self.removeUnusedGates(unused_gate_candidates)
    unused.update(redundant)
    self.updatePos(output_assoc)
    self.setGateLevels()
    return unused


  def init(self, ordered_gate = True) :
    if not ordered_gate :
      self.setGateOutputs()
    self.removeConstantGates()
    self.setGateLevels()

  def setGateLevels(self) :
    self.alias2level = {x : 0 for x in self.pis}
    if self.constant_gate_alias is not None :
      self.alias2level[self.constant_gate_alias] = 0
    self.getTopologicalOrder()
    for x in self.topological_order :
      if len(self.getGateInputs(x)) > 0 :
        self.alias2level[x] = 1 + max(self.alias2level[y] for y in self.getGateInputs(x))
      # else the gate is a constant gate which has level 0

  def removeConstantGates(self) :
    constant_gates = {x for x in self.getGateAliases() if len(self.getGateInputs(x)) == 0}
    substitution = {x : None for x in constant_gates}
    while constant_gates :
      alias = constant_gates.pop()
      for x in self.getGateOutputs(alias) :
        gate = self.getGate(x)
        gate.substitute(substitution)
        if gate.isConstant() :
          constant_gates.add(x)
          substitution[x] = None
      self.removeGate(alias)
      if self.isPO(alias) :
        for out_idx in getAllIndices(self.pos, alias) :
          self.pos[out_idx] =  self.getConstantAlias(alias)
          self.pos_set = set(self.pos)

      

  # For large circuits the recursive dfs search seems to be potentially problematic under Python.
  # Apriori we do not know the depth of the circuit.
  # Thus, we would have to set the recursion limit to a sufficiently large value such that the 
  # considered circuits can be analysed with respect to this limit.
  # This does not seem to be a clean solution.
  # If the recursive version shall still be used set the recursion limit appropriately with:
  # sys.setrecursionlimit(x)
  def getTopologicalOrderRecursive(self) :
    seen = set()
    self.topological_order = [None] * len(self.alias2gate)
    order = [len(self.topological_order), self.topological_order]
    for x in self.pis :
      for y in self.alias2outputs[x] :
        if y not in seen :
          self.dfsVisit(y, seen, order)
    
    if len(seen) != len(self.alias2gate) :
      assert len(seen) == len(self.alias2gate) - 1
      assert self.constant_gate_alias is not None
      self.topological_order[0] = self.constant_gate_alias
    

  def dfsVisit(self, gate_alias, seen, order) :
    successors = self.alias2outputs[gate_alias]
    for x in successors :
      if not x in seen :
        self.dfsVisit(x, seen, order)
    seen.add(gate_alias)
    order[1][order[0] - 1] = gate_alias
    order[0] -= 1

  # More Python friendly style of sorting the aliases
  # Replace the recursion by an iteration
  def getTopologicalOrder(self) :
    expanded = set()
    visited = set() # Only used for a debug check
    self.topological_order = [None] * len(self.alias2gate)
    order_index = len(self.topological_order) - 1
    # The pis shall be treated differently as the gates
    # Thus, we do not put them into the stack and handle them all at once
    for pi in self.pis :
      # There are two kinds of entries on the stack
      # alias, False -> add the children to the stack
      # alias, True  -> all children processed -> insert into ordering
      to_process_stack = []
      for x in self.alias2outputs[pi] :
        if x not in expanded :
          to_process_stack.append((x, False))
      while len(to_process_stack) > 0 :
        alias, children_processed = to_process_stack.pop()
        if alias in expanded :
          assert not children_processed
          continue
        if children_processed :
          self.topological_order[order_index] = alias
          order_index -= 1
          expanded.add(alias)
        else :
          # We try to expand a gate that is already on the current DFS path.
          if alias in visited :
            assert False, "Cycle detected"
          # Will get processed as soon as all outputs are processed
          to_process_stack.append((alias, True))
          visited.add(alias)
          for x in self.alias2outputs[alias] :
            if x not in expanded :
              to_process_stack.append((x, False))
    # The constant gate is not connected to the pis. Thus it needs to be handled separately.
    if len(expanded) != len(self.alias2gate) :
      assert len(expanded) == len(self.alias2gate) - 1
      assert self.constant_gate_alias is not None
      self.topological_order[0] = self.constant_gate_alias


  # table: A bitarray
  def addGate(self, gate_alias, inputs, table) :
    assert isinstance(table, bitarray.bitarray)
    self.max_var = max(self.max_var, gate_alias)
    assert len(table) == 2 ** len(inputs)
    assert isNormalised(table)
    for x in inputs :
      self.alias2outputs[x].add(gate_alias)
    self.alias2gate[gate_alias] = Gate(gate_alias, inputs, table)
    self.alias2outputs[gate_alias] = set()
    self.alias2level[gate_alias] = None

  def addGateUnsorted(self, gate_alias, inputs, table) :
    assert isinstance(table, bitarray.bitarray)
    self.max_var = max(self.max_var, gate_alias)
    assert len(table) == 2 ** len(inputs)
    assert isNormalised(table)
    self.alias2gate[gate_alias] = Gate(gate_alias, inputs, table)
    self.alias2outputs[gate_alias] = set()
    self.alias2level[gate_alias] = None

  def setGateOutputs(self) :
    pis_set = set(self.pis)
    # A PI may be an PO
    to_process = [x for x in self.pos if x not in pis_set]
    seen = set(to_process)
    while len(to_process) > 0 :
      alias = to_process.pop()
      for x in self.getGate(alias).inputs :
        self.alias2outputs[x].add(alias)
        if not x in seen and not x in pis_set:
          seen.add(x)
          to_process.append(x)
            
          
  def negateOutput(self, alias) :
    for i in getAllIndices(self.pos, alias) :
      self.negated_pos[i] = 1
  
  def toggleOutputNegation(self, alias) :
    for i in getAllIndices(self.pos, alias) :
      self.negated_pos[i] = 1 - self.negated_pos[i]


  def getOutputsToNegate(self) :
    positive_outputs = set()
    negative_outputs = set()
    for idx, out in enumerate(self.pos) :
      if self.negated_pos[idx] :
        negative_outputs.add(out)
      else :
        positive_outputs.add(out)
    outputs_in_both_polarities = positive_outputs.intersection(negative_outputs)
    negative_outputs.difference_update(positive_outputs)
    return negative_outputs, outputs_in_both_polarities