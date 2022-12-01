# import multiprocessing
import logging
import time
import random
import sys
import tempfile

from synthesiser import Synthesiser
from utils import Configuration
import reduceWithAbc

import blifIO
import aigerIO


class Synthesismanager :

  @staticmethod
  def getSpecification(spec, ordered_inputs = False) :
    if spec.endswith(".aig") or spec.endswith(".aag") :
      return aigerIO.getSpecification(spec)
    else :
      assert spec.endswith(".blif")
      return blifIO.getSpecification(spec, ordered_inputs)

  def __init__(self, spec_file, config : Configuration, ordered_spec = False) :
    logging.getLogger().setLevel(logging.INFO)
    self.specification = Synthesismanager.getSpecification(spec_file, ordered_spec)
    self.initial_nof_gates = self.specification.getNofGates()
    self.initial_depth = self.specification.getDepth()
    print(f"Initial Depth:     {self.initial_depth}")
    print(f"Initial Nof gates: {self.initial_nof_gates}")
    self.config = config
    if config.seed is None :
      self.randomSeed()
    else :
      self.setSeed(config.seed)

  def _printIntermediateResults(self, synth, iteration) :
    if self.config.synthesiseAig or iteration < self.config.runs - 1 :
      print(f"Results after run {iteration}")
    else :
      print("Final results")
    self.printStatistics()
    synth.printStatistics()
    if self.config.specification_log_dir is not None and iteration < self.config.runs - 1 :
      fname = f"{self.config.specification_log_dir}/intermediate_result_run_{iteration}.blif"
      self.writeSpecification(fname)

  def reduce(self, budget) :
    self.start = time.time()
    total_abc_time = 0
    reduced_by_abc = 0
    for i in range(self.config.runs) :
      synth = self._applyReduction(budget)
      self._printIntermediateResults(synth, i)
      if self.config.use_abc :
        circuit_size = self.specification.getNofGates()
        reduced, abc_time = self._applyABC(i)
        total_abc_time += abc_time
        print(f"ABC used time: {abc_time}")
        if reduced :
          reduced_by_abc += (circuit_size - self.specification.getNofGates())
          if self.config.specification_log_dir is not None and i < self.config.runs - 1 :
            fname = f"{self.config.specification_log_dir}/abc_run_{i}.blif"
            self.writeSpecification(fname)
          
    if self.config.synthesiseAig :
      print("Final results")
      if self.config.use_abc :
        print(f"Total ABC time: {total_abc_time}")
        print(f"Reduced by ABC: {reduced_by_abc}")
      self.printStatistics()

  def _applyReduction(self, budget) :
    synthesiser = Synthesiser(self.specification, self.config)
    return synthesiser.reduce(budget, self.config.initial_subcircuit_size, self.config.gate_size)

  def _applyABC(self, iteration) :
    abc_start_time = time.time()
    spec_suffix = ".aig" if self.config.synthesiseAig else ".blif"
    nof_gates = self.specification.getNofGates()
    reduced_aig_fname = None
    if self.config.specification_log_dir is not None :
      reduced_aig_fname = f"{self.config.specification_log_dir}/abc_result_run_{iteration}{spec_suffix}"
    with  tempfile.NamedTemporaryFile(mode = "w", suffix = spec_suffix, delete=True) as in_file, \
          tempfile.NamedTemporaryFile(mode = "w", suffix = spec_suffix, delete=True) if reduced_aig_fname is None else open(reduced_aig_fname, 'w') as out_file:
      self.writeSpecification(in_file.name, not self.config.synthesiseAig)
      in_file.flush()
      gate_count = reduceWithAbc.applyABC(in_file.name, out_file.name, self.config.abc_preprocess_cmds, self.config.abc_cmds, self.config.synthesiseAig)
      out_file.flush()
      spec = self.getSpecification(out_file.name)
      print(f"ABC #gates before: {nof_gates}; after: {spec.getNofGates()}")
      print(f"ABC gate count: {gate_count}; internal count: {spec.getNofGates()}")
      spec_reduced = spec.getNofGates() < nof_gates
      if spec_reduced :
        self.specification = spec
      else :
        print("ABC increased #gates -- ABC result is not used")
    abc_time = time.time() - abc_start_time
    return spec_reduced, abc_time

  def setSeed(self, value) :
    self.seed = value
    random.seed(value)

  def randomSeed(self) :
    random_seed = random.randrange(sys.maxsize)
    self.setSeed(random_seed)
    logging.info(f"Used seed: {random_seed}")

  def _getEllapsedTime(self) :
    return time.time() - self.start

  def printStatistics(self) :
    current_nof_gates = self.specification.getNofGates()
    current_depth = self.specification.getDepth()
    print(f"Total time: {self._getEllapsedTime()}")
    print(f"Initial #gates: {self.initial_nof_gates}; current #gates: {current_nof_gates}")
    print(f"Initial depth: {self.initial_depth}; current depth: {current_depth}")

  def writeSpecification(self, fname, writeBlif=True) :
    if writeBlif :
      blifIO.writeSpecification(fname, self.specification)
    else :
      aigerIO.writeSpecification(fname, self.specification)