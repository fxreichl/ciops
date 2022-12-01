# CIOPS

CIOPS (**CI**rcuit **OP**timization **S**ystem) is a tool for minimizing Boolean circuits and for the exact synthesis of Boolean circuits.
CIOPS is based on using a QBF (Quantified Booelan Formula) encoding for finding minimal representations of given Boolean circuits.

## Installing CIOPS

### Dependencies

To use CIOPS the following dependencies must be installed:
- [pybind11](https://github.com/pybind/pybind11)
- [bitarray](https://pypi.org/project/bitarray/)
- [CMake >= 3.4](https://cmake.org/)
- [GCC](https://gcc.gnu.org/)

Additionally, at least on of the following QBF solvers need to be installed.
- [QFUN](https://sat.inesc-id.pt/~mikolas/sw/qfun/)
- [miniQU](https://github.com/fslivovsky/miniQU)
- [QuAbS](https://github.com/ltentrup/quabs)

We recommend using the solver ***QFUN***. 
In addition to installing a solver also the path to the binary needs to be set in ***utils.py***. 

### Optional Dependencies

To use [ABC](https://people.eecs.berkeley.edu/~alanmi/abc/) for inprocessing, the ***ABC*** synthesis and verification system needs to be installed.
Additionally, the path to the ***ABC*** binary needs to be set in ***utils.py***. 

### Included Dependencies

To read and write AIGs (And-Inverter Graph) the [AIGER](https://github.com/arminbiere/aiger) library is used.

### Build

We only provide instructions for building CIOPS on a LINUX system.
```
git clone --recursive https://github.com/fxreichl/ciops
cd ciops/aiger_io
mkdir build && cd build
cmake ..
make
```

## Usage

CIOPS is mainly intended for circuit minimization but also supports exact synthesis.
The goal of exact synthesis is to find a Boolean circuit that represents a given Boolean functions.
The generated circuit needs to be minimal, i.e. there is no other circuit representation of the given function with fewer gates.
Circuit minimization aims at reducing the number of gates in a given Boolean circuit.
While in circuit minimization no guarantee is given that there is no smaller representation, minimization works with significantly larger circuits.

### Exact Synthesis

Exact Synthesis is realized in ***exactSynthesiser.py***.
To run this script use:
```
exactSynthesiser.py <Specification> <Result> 
```
#### Inputs

- ```Specification``` the function to synthesize given in the [Berkeley Logic Interchange Format (BLIF)](http://www.cs.columbia.edu/~cs6861/sis/blif/index.html).
While BLIF is a format for specifying circuits it can also be used to directly specify a Boolean function by a truth table if a single gate representing the function is used.
- ```Result``` the file to which the resulting circuit shall be written. By default, the result is given as a BLIF. If the option ***--aig*** is used the result is given in the AIGER format (if the filename has the ***.aag*** extension the ASCII AIGER format is used otherwise the binary AIGER format is used).

The available options are listed if ***-h*** is used.

### Circuit Minimization

Circuit Minimization is realized in ***reduce.py***.
To run this script use:
```
reduce.py <Specification> <Result> <Limit>
```
#### Inputs

- ```Specification``` the circuit to minimize. Given either in the BLIF or in the AIGER format.
- ```Result``` the file to which the resulting circuit shall be written. By default, the result is given as a BLIF. If the option ***--aig*** is used the result is given in the AIGER format (if the filename has the ***.aag*** extension the ASCII AIGER format is used otherwise the binary AIGER format is used).
- ```Limit``` the available time budget given in seconds.

The available options are listed if ***-h*** is used.


<!--

### Library Use

## How to Cite

## Contributors

-->


