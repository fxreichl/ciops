#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import time
import logging

import subcircuitSynthesiser
from utils import Configuration
import blifIO
import aigerIO


if __name__ == "__main__" :
  parser = argparse.ArgumentParser(description="QBF based circuit synthesis")  
  parser.add_argument('specification', metavar='SPEC',help='The specification')
  parser.add_argument('synthesised_circuit', metavar='SYN',help='The synthesised circuit')
  parser.add_argument('--gs', nargs='?', const=2, type=int, help='The number of inputs of the gates')
  parser.add_argument('--log-enc', nargs=1, help='Save the generated encodings in the given directory')
  parser.add_argument('-N', action='store_false',help='Non trivial')
  parser.add_argument('-A', action='store_false',help='All steps')
  parser.add_argument('-R', action='store_false',help='No Reapplication')
  parser.add_argument('-C', action='store_false',help='Ordered steps')
  parser.add_argument('-input-vars', action='store_false',help='Do not use gate input vars')
  parser.add_argument('-aig', action='store_true',help='Generate an AIG instead of a blif')
  args = parser.parse_args()
  logging.getLogger().setLevel(logging.INFO)
  spec = blifIO.getSpecification(args.specification)
  config = Configuration()
  if args.gs :
    config.gate_size = args.gs
  else :
    config.gate_size = 2
  if args.aig :
    assert config.gate_size == 2
  config.useTrivialRuleConstraint = args.N
  config.useAllStepsConstraint = args.A
  config.useNoReapplicationConstraint = args.R
  config.useOrderedStepsConstraint = args.C
  config.useGateInputVariables = args.input_vars
  config.synthesiseAig = args.aig
  synth = subcircuitSynthesiser.SubcircuitSynthesiser(spec, config)

  begin = time.time()
  gates = spec.getGateAliases()
  size = synth.bottomUpReduction(gates, config)
  end = time.time()

  print(f"Total time: {end - begin}")
  print(f"Minimal size: {size}")

  if args.aig :
    aigerIO.writeSpecification(args.synthesised_circuit, spec)
  else :
    blifIO.writeSpecification(args.synthesised_circuit, spec)
