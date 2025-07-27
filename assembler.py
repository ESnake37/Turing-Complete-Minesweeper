import re
import tkinter as tk
from tkinter import filedialog



OPCODE_MAP = {
    #  ALU
    'NOP'     : '000000',
    'ADD'     : '000001',
    'SUB'     : '000010',
    'MUL'     : '000011',
    'DIV'     : '000100',
    'MOD'     : '000101',
    'NEG'     : '000110',
    'NOT'     : '000111',
    'AND'     : '001000',
    'OR'      : '001001',
    'XOR'     : '001010',
    'ASHR'    : '001011',
    'SHL'     : '001100',
    'SHR'     : '001101',
    'CMP'     : '001110',
    'JMP'     : '001111',
    #  MEMORY
    'CALL'    : '010000',
    'RET'     : '010001',
    'SW'      : '010010',
    'LW'      : '010011',
    'PUSH'    : '010100',
    'POP'     : '010101',
    #  IO
    'RAND'    : '100000',
    'OUTSEG'  : '100001',
    'PSET'    : '100010',
    #  SYSTEM

}

CONDITION_MAP = {
    'EQ'      : '001',
    'NE'      : '010',
    'LT'      : '011',
    'LE'      : '100',
    'GT'      : '101',
    'GE'      : '110',
    'NEV'     : '111'
}

CONDITION_PSEUDO_INSTRUCTIONS = {
    'BEQ'     : '001',
    'BNE'     : '010',
    'BLT'     : '011',
    'BLE'     : '100',
    'BGT'     : '101',
    'BGE'     : '110',
    'BNEV'    : '111'
}

PSEUDO_INSTRUCTIONS = {
    'MOV'     : '000001',
    'INC'     : '000001',
    'DEC'     : '000010',
    'CLR'     : '000001',
    'SQ'      : '000011',
    'GET'     : '000001',
    'SETCOLOR': '000001'
}

# 寄存器映射
REGISTER_MAP = {
    **{f'R{i}': i for i in range(30)},
    'IN'      : 30,
    'COLOR'   : 31
}


CONST_TABLE = {}  # 存储 CONST 表
LABEL_TABLE = {}  # 存储 LABEL 表



def is_immediate(token):
    """判断操作数是否为立即数（支持二进制、八进制、十进制、十六进制和负数）"""
    immediate_pattern = re.compile(r"^-?(0b[01]+|0x[0-9A-Fa-f]+|0o[0-7]+|\d+)$")
    return bool(immediate_pattern.match(token))


def parse_const_definition(line, line_num):
    """解析 CONST 定义"""
    parts = line.split()
    if len(parts) != 3:
        raise ValueError(f"第{line_num}行错误：CONST 语法错误，应为 'CONST 符号名 值' 格式\n> {line}")
    symbol = parts[1]
    val_token = parts[2]
    if symbol in CONST_TABLE:
        raise ValueError(f"第{line_num}行错误：CONST '{symbol}' 重复定义\n> {line}")
    CONST_TABLE[symbol] = val_token


def parse_label_definition(line, line_num, instr_addr):
    """解析 LABEL 定义"""
    label, _, _ = line.partition(':')
    label = label.strip()
    if not label:
        raise ValueError(f"第{line_num}行错误：LABEL 语法错误，标签名不能为空\n> {line}")
    if label in LABEL_TABLE:
        raise ValueError(f"第{line_num}行错误：LABEL '{label}' 重复定义\n> {line}")
    LABEL_TABLE[label] = instr_addr
    return instr_addr


def parse_const_label(lines):
    """第一轮解析：解析 CONST 和 LABEL 定义"""
    instr_addr = 0
    line_map = []  # 原始汇编代码行数
    assembly_lines = []  # 去掉首尾空格、空行、注释行、 CONST 和 LABEL 定义行的汇编代码

    # 处理首尾空格、空行和注释行
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        line_map.append(line_num)
        if not line or line.startswith('#'):
            continue

        # CONST 行
        if line.startswith('CONST'):
            parse_const_definition(line, line_num)

        # LABEL 行
        elif ':' in line:
            instr_addr = parse_label_definition(line, line_num, instr_addr)

        # 普通指令行
        else:
            parts = line.split()
            op = parts[0]
            operands = parts[1:]
            if operands and operands[-1] in CONST_TABLE:
                operands[-1] = CONST_TABLE[operands[-1]]
            if operands and is_immediate(operands[-1]):
                imm = int(operands[-1], 0)
                if imm < 0 or imm >= 2048:
                    instr_addr += 1
            if op == "CMP":
                instr_addr += 1
            elif op in CONDITION_PSEUDO_INSTRUCTIONS:
                instr_addr += 2
            instr_addr += 1
            assembly_lines.append(line)
    return assembly_lines, line_map


def replace_const_label(lines):
    """第二轮解析：替换 CONST 和 LABEL"""
    resolved_lines = []
    for _, line in enumerate(lines, 1):
        parts = line.split()
        op = parts[0]
        operands = parts[1:]
        replaced_operands = []
        for token in operands:
            if token in CONST_TABLE:
                replaced_operands.append(CONST_TABLE[token])
            elif token in LABEL_TABLE:
                replaced_operands.append(LABEL_TABLE[token])
            else:
                replaced_operands.append(token)
        replaced_line = ' '.join([op] + [str(token) for token in replaced_operands])
        resolved_lines.append(replaced_line)
    return resolved_lines


def parse_register(token, line_num):
    """解析寄存器编号"""
    if token in REGISTER_MAP:
        return REGISTER_MAP[token]
    raise ValueError(f"第{line_num}行错误：无效寄存器名 '{token}'")


def parse_instruction(lines, line_map, assembly_lines):
    """第三轮解析：处理指令并生成机器码"""
    machine_code = []
    final_lines = []

    for i, line in enumerate(lines):
        line_num = line_map[i]
        parts = line.split()
        op = parts[0]
        operands = parts[1:]

        # 处理 COND 字段
        cond_code = '000'  # 默认条件码
        if operands and operands[0] in CONDITION_MAP:
            cond_code = CONDITION_MAP[operands[0]]
            operands = operands[1:]

        # 处理条件跳转伪指令
        if op in CONDITION_PSEUDO_INSTRUCTIONS:
            op_code = CONDITION_PSEUDO_INSTRUCTIONS[op]
            if len(operands) != 3:
                raise ValueError(f"第{line_num}行错误：{op} 指令需要三个操作数")
            rs1 = parse_register(operands[0], line_num)
            jmp_addr = int(operands[2], 0)
            jmp_addr = f"{jmp_addr & ((1 << 11) - 1):011b}"
            if is_immediate(operands[1]):
                rs2 = int(operands[1], 0)
                rs2 = f"{rs2 & ((1 << 11) - 1):011b}"
                machine_code.append(f"001110 000 00000 {rs1:05b} 10{rs2}")
            else:
                rs2 = parse_register(operands[1], line_num)
                machine_code.append(f"001110 000 00000 {rs1:05b} 00000000{rs2:05b}")
            machine_code.append("00000000000000000000000000000000")
            machine_code.append(f"001111 {op_code} 00000 00000 10{jmp_addr}")

        # 处理其他伪指令
        elif op in PSEUDO_INSTRUCTIONS:
            op_code = PSEUDO_INSTRUCTIONS[op]

            if op == 'MOV':
                if len(operands) != 2:
                    raise ValueError(f"第{line_num}行错误：{op} 指令需要两个操作数")
                rd = parse_register(operands[0], line_num)
                rs1 = 0
                if is_immediate(operands[1]):
                    rs2 = int(operands[1], 0)
                    if 0 <= rs2 < 2048:
                        rs2 = f"{rs2 & ((1 << 11) - 1):011b}"
                        machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 10{rs2}")
                    else:
                        rs2 = format(rs2 & 0xFFFFFFFF, '032b')
                        machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 0100000000000")
                        machine_code.append(f"{rs2}")
                else:
                    rs2 = parse_register(operands[1], line_num)
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

            elif op == 'INC':
                if len(operands) != 1:
                    raise ValueError(f"第{line_num}行错误：{op} 指令需要一个操作数")
                rd = parse_register(operands[0], line_num)
                rs1 = parse_register(operands[0], line_num)
                rs2 = 1
                machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 10000000{rs2:05b}")

            elif op == 'DEC':
                if len(operands) != 1:
                    raise ValueError(f"第{line_num}行错误：{op} 指令需要一个操作数")
                rd = parse_register(operands[0], line_num)
                rs1 = parse_register(operands[0], line_num)
                rs2 = 1
                machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 10000000{rs2:05b}")

            elif op == 'CLR':
                if len(operands) != 1:
                    raise ValueError(f"第{line_num}行错误：{op} 指令需要一个操作数")
                rd = parse_register(operands[0], line_num)
                rs1 = 0
                rs2 = 0
                machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

            elif op == 'SQ':
                if len(operands) != 2:
                    raise ValueError(f"第{line_num}行错误：{op} 指令需要两个操作数")
                rd = parse_register(operands[0], line_num)
                rs1 = parse_register(operands[1], line_num)
                rs2 = parse_register(operands[1], line_num)
                machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

            elif op == 'GET':
                if len(operands) != 1:
                    raise ValueError(f"第{line_num}行错误：{op} 指令需要一个操作数")
                rd = parse_register(operands[0], line_num)
                machine_code.append(f"{op_code} {cond_code} {rd:05b} 11110 0000000000000")

            elif op == 'SETCOLOR':
                if len(operands) != 1:
                    raise ValueError(f"第{line_num}行错误：{op} 指令需要一个操作数")
                if is_immediate(operands[0]):
                    rs2 = int(operands[0], 0)
                    if 0 <= rs2 < 2048:
                        rs2 = f"{rs2 & ((1 << 11) - 1):011b}"
                        machine_code.append(f"{op_code} {cond_code} 11111 00000 10{rs2}")
                    else:
                        rs2 = format(rs2 & 0xFFFFFFFF, '032b')
                        machine_code.append(f"{op_code} {cond_code} 11111 00000 0100000000000")
                        machine_code.append(f"{rs2}")
                else:
                    rs2 = parse_register(operands[0], line_num)
                    machine_code.append(f"{op_code} {cond_code} 11111 00000 00000000{rs2:05b}")

        # 处理真指令
        elif op in OPCODE_MAP:
            op_code = OPCODE_MAP[op]

            # 处理立即数
            if operands and is_immediate(operands[-1]):
                rs2 = int(operands[-1], 0)
                # 立即数小于等于11位
                if 0 <= rs2 < 2048:
                    rs2 = f"{rs2 & ((1 << 11) - 1):011b}"
                    rs2 = "10" + rs2
                # 立即数大于11位小于32位
                else:
                    imm = format(rs2 & 0xFFFFFFFF, '032b')
                    rs2 = '0100000000000'
                if len(operands) == 1:  # 只有一个操作数
                    rd = 0
                    rs1 = 0
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} {rs2}")
                elif len(operands) == 2:  # 有两个操作数
                    if op in ['CMP', 'SW', 'PSET']:
                        rd = 0
                        rs1 = parse_register(operands[0], line_num)
                        machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} {rs2}")
                    elif op == 'NOT':
                        rd = parse_register(operands[0], line_num)
                        rs1 = 0
                        machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} {rs2}")
                else:  # 有三个操作数
                    rd = parse_register(operands[0], line_num)
                    rs1 = parse_register(operands[1], line_num)
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} {rs2}")
                if rs2 == '0100000000000':
                    machine_code.append(f"{imm}")
                if op == 'CMP':
                    machine_code.append(f"00000000000000000000000000000000")

            # 无立即数
            else:
                if op in ['NOP', 'RET']:
                    if len(operands) != 0:
                        raise ValueError(f"第{line_num}行错误：{op} 指令需要零个操作数")
                    rd = 0
                    rs1 = 0
                    rs2 = 0
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

                elif op in ['ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'AND', 'OR', 'XOR', 'SHL', 'SHR']:
                    if len(operands) != 3:
                        raise ValueError(f"第{line_num}行错误：{op} 指令需要三个操作数")
                    rd = parse_register(operands[0], line_num)
                    rs1 = parse_register(operands[1], line_num)
                    rs2 = parse_register(operands[2], line_num)
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

                elif op in ['NOT']:
                    if len(operands) != 2:
                        raise ValueError(f"第{line_num}行错误：{op} 指令需要两个操作数")
                    rd = parse_register(operands[0], line_num)
                    rs1 = 0
                    rs2 = parse_register(operands[1], line_num)
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

                elif op in ['CMP', 'SW', 'PSET']:
                    if len(operands) != 2:
                        raise ValueError(f"第{line_num}行错误：{op} 指令需要两个操作数")
                    rd = 0
                    rs1 = parse_register(operands[0], line_num)
                    rs2 = parse_register(operands[1], line_num)
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")
                    if op == 'CMP':
                        machine_code.append("00000000000000000000000000000000")

                elif op in ['LW']:
                    if len(operands) != 2:
                        raise ValueError(f"第{line_num}行错误：{op} 指令需要两个操作数")
                    rd = parse_register(operands[0], line_num)
                    rs1 = parse_register(operands[1], line_num)
                    rs2 = 0
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

                elif op in ['PUSH', 'OUTSEG']:
                    if len(operands) != 1:
                        raise ValueError(f"第{line_num}行错误：{op} 指令需要一个操作数")
                    rd = 0
                    rs1 = 0
                    rs2 = parse_register(operands[0], line_num)
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

                elif op in ['POP', 'RAND']:
                    if len(operands) != 1:
                        raise ValueError(f"第{line_num}行错误：{op} 指令需要一个操作数")
                    rd = parse_register(operands[0], line_num)
                    rs1 = 0
                    rs2 = 0
                    machine_code.append(f"{op_code} {cond_code} {rd:05b} {rs1:05b} 00000000{rs2:05b}")

        else:
            raise ValueError(f"第{line_num}行错误：不支持的操作符 '{op}'")

        # 添加对应的原始汇编注释行
        final_lines.append(assembly_lines[i])
        if operands and is_immediate(operands[-1]):
            imm_val = int(operands[-1], 0)
            if imm_val < 0 or imm_val >= 2048:
                final_lines.append('')
        if op in CONDITION_PSEUDO_INSTRUCTIONS:
            final_lines.append('')
            final_lines.append('')
        if op == 'CMP':
            final_lines.append('')

    return machine_code, final_lines



def open_file_dialog():
    """弹出文件选择框"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    file_path = filedialog.askopenfilename(title="选择汇编代码文件", filetypes=[("汇编文件", "*.asm"), ("所有文件", "*.*")])
    return file_path


def save_file_dialog():
    """弹出文件保存框"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    file_path = filedialog.asksaveasfilename(
        title="保存机器码文件",
        defaultextension=".hex",
        filetypes=[
            ("十六进制机器码文件 (*.hex)", "*.hex"),
            ("二进制机器码文件 (*.bin)", "*.bin"),
            ("所有文件", "*.*")
        ]
    )
    return file_path


def read_assembly_file(file_path):
    """读取汇编文件并返回每行内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        return lines
    except FileNotFoundError:
        print(f"错误: 找不到文件 {file_path}")
        return []
    except IOError as e:
        print(f"错误: 无法读取文件 {file_path}，原因: {e}")
        return []
    except UnicodeDecodeError as e:
        print(f"错误: 无法解码文件 {file_path}，请检查文件编码。")
        return []


def write_machine_code(machine_code, final_lines, output_file):
    """将机器码写入文件"""
    is_hex = output_file.endswith('.hex')
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            for i, (code_line, asm_line) in enumerate(zip(machine_code, final_lines), 1):
                bin_str = code_line.replace(' ', '')  # 去掉空格
                if len(bin_str) != 32:
                    error_details = (
                        f"第 {i} 行机器码位数错误: 应为32位，实际为{len(bin_str)}位\n"
                        f"├─ 汇编行: {asm_line.strip()}\n"
                        f"└─ 生成的机器码: {bin_str}"
                    )
                    raise ValueError(error_details)
                if is_hex:
                    hex_str = f"0x{int(bin_str, 2):08X}"
                    file.write(f"{hex_str}  # {asm_line.strip()}\n")
                else:
                    file.write(f"{bin_str}\n")

        print(f"机器码已保存到：{output_file}")
    except IOError as e:
        print(f"错误: 无法写入文件 {output_file}，原因: {e}")
    except ValueError as ve:
        print(f"机器码转换错误：{ve}")


def main():
    """主程序入口"""
    input_file = open_file_dialog()
    if not input_file:
        print("未选择输入文件。")
        return

    output_file = save_file_dialog()
    if not output_file:
        print("未选择输出文件。")
        return

    lines = read_assembly_file(input_file)
    if not lines:
        return

    print(f"开始汇编: {input_file}")
    print(f"找到 {len(lines)} 行代码")

    # 第一轮解析：解析 CONST 和 LABEL 定义
    assembly_lines, line_map = parse_const_label(lines)

    # 第二轮解析：替换 CONST 和 LABEL
    resolved_lines = replace_const_label(assembly_lines)

    # 第三轮解析：处理指令并生成机器码
    machine_code, final_lines = parse_instruction(resolved_lines, line_map, assembly_lines)

    print(f"生成 {len(machine_code)} 条机器码")

    # 输出机器码到文件
    write_machine_code(machine_code, final_lines, output_file)


if __name__ == "__main__":
    main()