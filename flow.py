# --- *coding=UTF-8* ---

flow_changing_mnemonics = ['bra'] # ret looks more like an instruction, call doesn't change the flow
finishing_mnemonics = ['ret']
if_mnemonics = ['bra']


def indent(text):
    return '\n'.join('    ' + se 
                   for se in
                   text.split('\n'))


def match_events(mess, order):
    if len(mess) != len(order):
        return False

    started_events = set()
    for joinsplit, (event_type, event_number) in zip(mess, order):
        if not isinstance(joinsplit, event_type):
            return False
        if event_number in started_events:
            started_events.remove(event_number)
        else:
            started_events.add(event_number)
    return not started_events


class FunctionBoundsException(Exception):
    pass

class FlowDetectError(Exception):
    pass


class IFFlowType:
    def __init__(self, branch):
        self.branch = branch
    
    def to_str(self, blocks):
        if len(blocks) != 1:
            raise ValueError("Wrong number of blocks for an if")
        return 'if (not branch@{0}) {1}'.format(self.branch.addr, blocks[0])


class IFElseFlowType:
    def __init__(self, branch):
        self.branch = branch
    
    def to_str(self, blocks):
        if len(blocks) != 2:
            raise ValueError("Wrong number of blocks for an if-else")
        return 'if (not branch@{0}) {1} else {2}'.format(self.branch.addr, blocks[0], blocks[1])


class FlowContainer:
    def __init__(self):
        self.flow = None

    def __str__(self):
        flow_elm_texts = []
        for flow_element in self.flow:
            flow_elm_texts.append(indent(str(flow_element)))

        flow_text = '\n\n'.join(flow_elm_texts)

        return flow_text

    def apply_instruction_analyzer(self, analyzer):
        for element in self.flow:
            element.apply_instruction_analyzer(analyzer)


class ControlStructure(FlowContainer):
    def __init__(self, code, joinsplits):
        FlowContainer.__init__(self)
        self.instructions = code
        self.find_closures(joinsplits)
        self.find_type()

    def find_closures(self, joinsplits):
        """Tries to find big spaces in between the outermost entangled mess of jumps.
        """
        if len(joinsplits) == 0:
            raise ValueError("A control structure must have joins and splits")

        # step 1: find the entangled mess jumps        
        mess = set([joinsplits[0]])
        left_joinsplits = set(joinsplits)
        left_joinsplits.remove(joinsplits[0])

        while True:
            intersections = set()
            for joinsplit in left_joinsplits:
                # if any item intersects any from mess, add to mess
                # otherwise mess found
                for item in mess:
                    if joinsplit.intersects(item):
                        intersections.add(joinsplit)
                        #print 'i', joinsplit, item

            if not intersections:
                break
            left_joinsplits.difference_update(intersections)
            mess.update(intersections)

        for item in list(mess):
            for joinsplit in left_joinsplits:
                if item.matches(joinsplit):
                    mess.add(joinsplit)

        # step 2: find spaces between all the jumps
        splitjoin_indices = [] # first, last pairs

        previous_splitjoin_index = 0
        for i, splitjoin in enumerate(joinsplits):
            if splitjoin in mess:
                splitjoin_indices.append((previous_splitjoin_index, i))
                previous_splitjoin_index = i
        
        # step 3: extract code and splitjoins
        splitjoin_slices = [] # splitjoins, instructions, instruction_offser triples

        for first_index, last_index in splitjoin_indices:
            # do not include boundary splitjoins
            sjs = joinsplits[first_index + 1:last_index]
            offset = joinsplits[first_index].index
            start_instructions = joinsplits[first_index].index
            end_instructions = joinsplits[last_index].index
            instructions = self.instructions[start_instructions:end_instructions]
            if instructions:
                splitjoin_slices.append((sjs, instructions, offset))
        
        '''
        print joinsplits
        print zip(*splitjoin_slices)[0]
        print sorted(mess)
        raw_input()
        '''
        # step 4: generate closures
        closures = []
        
        for sjs, instructions, instruction_offset in splitjoin_slices:
            for splitjoin in sjs:
                splitjoin.offset(instruction_offset)
            closures.append(Closure(instructions, sjs))
        
        self.mess = mess
        self.flow = closures        

    def find_type(self):
        def keyfunction(splitjoin):
            isjoin = isinstance(splitjoin, Join) # True will put it later
            if isjoin:
                order = -splitjoin.source # joins with earlier source are outer
            else:
                order = -splitjoin.destination # joins further out are earlier
            return splitjoin.index, isjoin, order

        mess = sorted(self.mess, key=keyfunction)
        
        # try if..
        events = [(Split, 0), (Join, 0)]
        if match_events(mess, events):
            self.type = IFFlowType(mess[0].cause)
        else:
            # try if..else
            events = [(Split, 0), (Split, 1), (Join, 0), (Join, 1)]
            if match_events(mess, events):
                self.type = IFElseFlowType(mess[0].cause)
            else:
                self.type = None
            

    def __repr__(self):
        return 'cs ' + self.instructions[0].addr + ' ' + self.instructions[-1].addr

    def __str__(self):
        if self.type is not None:
            return self.type.to_str(self.flow)

        if self.flow is None:
            return 'UnparsedFlowPattern {{{{\n{0}\n}}}}'.format(indent(str(LinearCode(self.instructions))))
        else:
            return 'FlowPattern {{{{\n{0}\n}}}}'.format(FlowContainer.__str__(self))


class LinearCode:
    def __init__(self, code):
        self.instructions = code

    def apply_instruction_analyzer(self, analyzer):
        return analyzer(self.instructions)

    def __repr__(self):
        return 'lc ' + self.instructions[0].addr + ' ' + self.instructions[-1].addr

    def __str__(self):
        return '\n'.join(map(str,self.instructions))


class Closure(FlowContainer):
    """Closure: code, control, code, control, ..."""
    def __init__(self, code, joinsplits):
        self.instructions = code
        self.flow = None
        if joinsplits:
            self.find_flow_patterns(joinsplits)
        else:
            self.flow = [LinearCode(code)]

    def find_flow_patterns(self, joinsplits):
        """Tries to find smallest possible control structures and big spaces between them.
        """
        control_structures = []

        flow_control_joinsplit_index = None
        current_forward_references = []
        linear_start_index = 0

        #print 'flow', joinsplits

        for i, joinsplit in enumerate(joinsplits):
            if linear_start_index is not None: # was in linear flow mode
                # commit results
                if linear_start_index != joinsplit.index:
                    control_structures.append(LinearCode(self.instructions[linear_start_index:joinsplit.index]))

                # switch modes
                linear_start_index = None
                flow_control_joinsplit_index = i
            
            # control flow find mode only
            if joinsplit.get_referenced_index() > joinsplit.index: # forward reference. add it
                current_forward_references.append(joinsplit)
            elif joinsplit.get_referenced_index() < joinsplit.index: # backward reference. remove the other one
                reference_index = None
                for y, reference in enumerate(current_forward_references):
                    if reference.matches(joinsplit):
                        reference_index = y

                if reference_index is None:
                    raise FlowDetectError("A past jumpsplit referred to can't be found: {0}".format(joinsplit))
                current_forward_references.pop(reference_index)
            else:
                raise FlowDetectError("Found self jump, not sure what to do")

            if len(current_forward_references) == 0: # no jumps/splits: must be linear from now on
                # switch modes
                linear_start_index = joinsplit.index

                #commit results
                subjoinsplits = joinsplits[flow_control_joinsplit_index:i + 1]

                instructions_start_index = subjoinsplits[0].index
                instructions_end_index = subjoinsplits[-1].index
                subinstructions = self.instructions[instructions_start_index:instructions_end_index]

                for joinsplit in subjoinsplits:
                    joinsplit.offset(instructions_start_index)
                    
                cs = ControlStructure(subinstructions, subjoinsplits)
                control_structures.append(cs)


        if linear_start_index is None:
            raise FlowDetectError("After evalutaing joinsplits, some are left")
        
        if linear_start_index < len(self.instructions):
            control_structures.append(LinearCode(self.instructions[linear_start_index:]))

        self.flow = control_structures    

    def __str__(self):
        return '{{\n{0}\n}}'.format(FlowContainer.__str__(self))


class Function(Closure):
    def __init__(self, code, index):
        self.address = code[index].address
        self.index = index
        self.instructions = self.find(code)
        self.flow = None
        self.detect_flow()

    # TODO: Make this a static method instead
    def find(self, code):
        """Assumes nothing will jump to the function from outside"""
        branches_outside = [] # list of target addresses
        for i in range(self.index, len(code)):
            instruction = code[i]
            current_address = instruction.address
            if instruction.mnemonic in flow_changing_mnemonics:
                if instruction.target < self.address:
                    raise CodeError("branch to before function start " + str(instruction))
                if instruction.target > current_address:
                    branches_outside.append(instruction.target)
            elif instruction.mnemonic in finishing_mnemonics:
                # prune branches outside
                new_outside_branches = []
                for branch_target in branches_outside:
                    if branch_target > current_address:
                        new_outside_branches.append(branch_target)
                branches_outside = new_outside_branches
                
                # check if found last return
                if not branches_outside:
                    return code[self.index:i + 1]
                '''
                else:
                    print instruction.addr, [hex(branch) for branch in branches_outside]
                '''
        
        raise FunctionBoundsException("function at {0} doesn't finish within the given code".format(hex(self.address)))

    def get_index(self, address):
        for i, instruction in enumerate(self.instructions):
            if instruction.address == address:
                return i
        raise ValueError("Address {0} out of function range".format(address))

    def find_jumps(self):
        jumps = []
        for i, instruction in enumerate(self.instructions):
            if instruction.mnemonic in flow_changing_mnemonics:
                source = self.get_index(instruction.address)
                destination = self.get_index(instruction.target)
                conditional = (instruction.condition != '')
                jumps.append((instruction, source, destination, conditional))
        return jumps

    def detect_flow(self):
        jumps = self.find_jumps()
        joinsplits = jumps_to_joinsplits(jumps)
        self.find_flow_patterns(joinsplits)
    
    def __str__(self):
        return '\n// {0}\nf_{0}(...) {1}\n'.format(hex(self.address), Closure.__str__(self))


class Split:
    def __init__(self, cause, index, destination, conditional):
        self.cause = cause
        self.index = index
        self.destination = destination
        self.conditional = conditional

    def get_referenced_index(self):
        return self.destination

    def matches(self, join):
        if not isinstance(join, Join):
            return False
        return join.source == self.index

    def offset(self, offset):
        self.index -= offset
        self.destination -= offset

    def intersects(self, other):
        # be super extra careful with that
        if isinstance(other, Split):
            if self.destination == other.destination: # two jumps to the same place never intersect
                return False
            if self.index < self.destination: # forward jump
                start_inside = (self.index < other.index <= self.destination)
                end_inside = (self.index <= other.destination < self.destination)        
            else:
                start_inside = (self.destination < other.index < self.index)
                end_inside = (self.destination <= other.destination < self.index)
        else: # intersect with a Join
            if self.destination == other.index: # two jumps to the same place never intersect
                return False
            if self.index < self.destination: # forward jump
                start_inside = (self.index < other.source <= self.destination)
                end_inside = (self.index <= other.index < self.destination)
            else:
                start_inside = (self.destination < other.source < self.index)
                end_inside = (self.destination <= other.index < self.index)
        return start_inside != end_inside # one inside, other outside: intersection


    def __repr__(self):
        return 's {0} {1}'.format(self.index, self.get_referenced_index())


class Join:
    def __init__(self, cause, index, source):
        self.cause = cause
        self.source = source
        self.index = index

    def get_referenced_index(self):
        return self.source

    def matches(self, split):
        if not isinstance(split, Split):
            return False
        return split.index == self.source

    def offset(self, offset):
        self.index -= offset
        self.source -= offset

    def intersects(self, other):
        if isinstance(other, Join):
            if self.index == other.index: # two jumps to the asme place never intersect
                return False
            if self.source < self.index: # forward jump
                start_inside = (self.source < other.source <= self.index)
                end_inside = (self.source <= other.index < self.index)
            else:
                start_inside = (self.index < other.source < self.source)
                end_inside = (self.index <= other.index < self.source)
            return start_inside != end_inside # one inside, other outside: intersection
        else:
            return other.intersects(self)

    def __repr__(self):
        return 'j {0} {1}'.format(self.index, self.get_referenced_index())


def jumps_to_joinsplits(jumps):
    """Unifies joins and splits for easier processing
    """

    # Phase 1: collect all flow changes in an unified form
    # Warning Achtung Внимание: control flow jumps occur IMMEDIATELY AFTER the branch instruction
    joinsplits = []
    for cause, source, destination, conditional in jumps:
        joinsplits.append(Split(cause, source + 1, destination, conditional))
        joinsplits.append(Join(cause, destination, source + 1))

    # Phase 2: linearize according to the code layout and put splits before joins
    def keyfunction(splitjoin):
        isjoin = isinstance(splitjoin, Join) # True will put it later
        if isjoin:
            order = -splitjoin.source # joins with earlier source are outer
        else:
            order = -splitjoin.destination # joins further out are earlier
        return splitjoin.index, isjoin, order
            
    return sorted(joinsplits, key=keyfunction)

