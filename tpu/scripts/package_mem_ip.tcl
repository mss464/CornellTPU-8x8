################################################################################
# package_mem_ip.tcl
#
# Packages the memory subsystem RTL into a reusable custom IP with:
#   - AXI4-Lite slave interface (s00_axi)    — control registers
#   - AXI-Stream slave interface (s00_axis)  — DMA write path
#   - AXI-Stream master interface (m00_axis) — DMA read path
#   - AXI4-Full slave interface (s01_axi)    — direct MMIO to sys_mem
#
# Usage:
#   vivado -mode batch -source scripts/package_mem_ip.tcl -tclargs \
#       -ip_name mem_subsys \
#       -part xczu3eg-sbva484-1-i \
#       -rtl_dir src/system \
#       -repo_out ip_repo
################################################################################

# Default values
set ip_name     "mem_subsys"
set part        "xczu3eg-sbva484-1-i"
set rtl_dirs    {}
set repo_out    ""
set ip_version  "1.0"
set ip_vendor   ""
set ip_library  "user"

# Parse command line arguments
proc parse_args {} {
    global argc argv
    global ip_name part rtl_dirs repo_out ip_version ip_vendor ip_library

    for {set i 0} {$i < $argc} {incr i} {
        set arg [lindex $argv $i]
        switch -exact -- $arg {
            "-ip_name" {
                incr i
                set ip_name [lindex $argv $i]
            }
            "-part" {
                incr i
                set part [lindex $argv $i]
            }
            "-rtl_dir" {
                incr i
                lappend rtl_dirs [lindex $argv $i]
            }
            "-repo_out" {
                incr i
                set repo_out [lindex $argv $i]
            }
            "-ip_version" {
                incr i
                set ip_version [lindex $argv $i]
            }
            "-ip_vendor" {
                incr i
                set ip_vendor [lindex $argv $i]
            }
            "-ip_library" {
                incr i
                set ip_library [lindex $argv $i]
            }
            "-help" {
                puts "Usage: vivado -mode batch -source package_mem_ip.tcl -tclargs <options>"
                puts "Options:"
                puts "  -ip_name <name>      IP core name (default: mem_subsys)"
                puts "  -part <part>         FPGA part number"
                puts "  -rtl_dir <dir>       RTL sources directory (repeatable)"
                puts "  -repo_out <dir>      Output IP repository directory"
                puts "  -ip_version <ver>    IP version (default: 1.0)"
                puts "  -ip_vendor <vendor>  IP vendor"
                puts "  -ip_library <lib>    IP library (default: user)"
                puts "  -help                Show this help message"
                exit 0
            }
            default {
                puts "WARNING: Unknown argument: $arg"
            }
        }
    }

    if {[llength $rtl_dirs] == 0} {
        puts "ERROR: at least one -rtl_dir is required"
        exit 1
    }
    if {$repo_out eq ""} {
        puts "ERROR: -repo_out is required"
        exit 1
    }
}

parse_args

# Normalize paths
set normalized_dirs {}
foreach d $rtl_dirs {
    lappend normalized_dirs [file normalize $d]
}
set rtl_dirs $normalized_dirs
set repo_out [file normalize $repo_out]

puts "============================================================"
puts "Memory Subsystem IP Packaging Script"
puts "============================================================"
puts "IP Name:     $ip_name"
puts "IP Version:  $ip_version"
puts "Part:        $part"
puts "RTL Dirs:    $rtl_dirs"
puts "Output Repo: $repo_out"
puts "============================================================"

file mkdir $repo_out

set proj_dir [file join [pwd] "pkg_${ip_name}_proj"]
file delete -force $proj_dir

################################################################################
# Step 1: Create project
################################################################################
puts "\n>>> Step 1: Creating project..."
create_project pkg_${ip_name} $proj_dir -part $part -force
set_property target_language Verilog [current_project]

################################################################################
# Step 2: Add RTL files
################################################################################
puts "\n>>> Step 2: Adding RTL files..."

set v_files {}
set sv_files {}
foreach rtl_dir $rtl_dirs {
    puts "  Scanning: $rtl_dir"
    set v_files [concat $v_files [glob -nocomplain -directory $rtl_dir *.v]]
    set sv_files [concat $sv_files [glob -nocomplain -directory $rtl_dir *.sv]]
}

# Filter: only include files needed for mem_top design (with compute tile)
set needed_files {
    mem_top.sv mem_ctrl.sv device_mem.sv axi_full_slave.sv
    tpu_slave_axi_lite.v tpu_slave_axi_stream.v tpu_master_axi_stream.v
    compute_ctrl.sv
    compute_tile.sv compute_core.sv scratchpad.sv mem_wrapper.sv sram_behavioral.sv
    mxu.sv systolic.sv pe.sv decoder.sv pc.sv
    vpu_simd.sv vpu.sv vpu_op.sv vec_regfile.sv
    dummy_unit.sv vadd.sv fp32_add.sv fp32_mul.sv fifo4.sv
}

set all_rtl_files [concat $v_files $sv_files]
set filtered_files {}
set seen_names {}
foreach f $all_rtl_files {
    set fname [file tail $f]
    if {$fname in $needed_files} {
        if {$fname in $seen_names} {
            puts "  Skipping duplicate: $fname (from [file dirname $f])"
        } else {
            lappend filtered_files $f
            lappend seen_names $fname
            puts "  Adding: $fname (from [file dirname $f])"
        }
    } else {
        puts "  Skipping: $fname (not in mem_top design)"
    }
}

if {[llength $filtered_files] == 0} {
    puts "ERROR: No matching RTL files found"
    close_project
    exit 1
}

foreach f $filtered_files {
    add_files -norecurse $f
}
foreach f $filtered_files {
    if {[string match "*.sv" $f]} {
        set_property file_type "SystemVerilog" [get_files $f]
    }
}

################################################################################
# Step 3: Create BRAM IPs
################################################################################
puts "\n>>> Step 3: Creating BRAM IPs..."

# blk_mem_gen_2: System Memory BRAM (32-bit × 8192, True Dual Port)
puts "  Creating blk_mem_gen_2 (System Memory - 32-bit x 8192)..."
create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 \
    -module_name blk_mem_gen_2

set_property -dict [list \
    CONFIG.Memory_Type {True_Dual_Port_RAM} \
    CONFIG.Write_Width_A {32} \
    CONFIG.Write_Depth_A {8192} \
    CONFIG.Read_Width_A {32} \
    CONFIG.Write_Width_B {32} \
    CONFIG.Read_Width_B {32} \
    CONFIG.Enable_A {Use_ENA_Pin} \
    CONFIG.Enable_B {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {false} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {false} \
    CONFIG.Use_Byte_Write_Enable {false} \
    CONFIG.Byte_Size {9} \
    CONFIG.Operating_Mode_A {WRITE_FIRST} \
    CONFIG.Operating_Mode_B {WRITE_FIRST} \
] [get_ips blk_mem_gen_2]

generate_target all [get_ips blk_mem_gen_2]
export_ip_user_files -of_objects [get_ips blk_mem_gen_2] -no_script -force

# blk_mem_gen_0: Scratchpad Bank BRAM (32-bit × 8192, True Dual Port)
# Used by mem_wrapper inside scratchpad.sv (8 banks × 1024 words each)
puts "  Creating blk_mem_gen_0 (Scratchpad Bank - 32-bit x 1024)..."
create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 \
    -module_name blk_mem_gen_0

set_property -dict [list \
    CONFIG.Memory_Type {True_Dual_Port_RAM} \
    CONFIG.Write_Width_A {32} \
    CONFIG.Write_Depth_A {1024} \
    CONFIG.Read_Width_A {32} \
    CONFIG.Write_Width_B {32} \
    CONFIG.Read_Width_B {32} \
    CONFIG.Enable_A {Use_ENA_Pin} \
    CONFIG.Enable_B {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {false} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {false} \
    CONFIG.Use_Byte_Write_Enable {false} \
    CONFIG.Byte_Size {9} \
    CONFIG.Operating_Mode_A {WRITE_FIRST} \
    CONFIG.Operating_Mode_B {WRITE_FIRST} \
] [get_ips blk_mem_gen_0]

generate_target all [get_ips blk_mem_gen_0]
export_ip_user_files -of_objects [get_ips blk_mem_gen_0] -no_script -force

# blk_mem_gen_1: Instruction BRAM (64-bit × 256, True Dual Port)
puts "  Creating blk_mem_gen_1 (Instruction BRAM - 64-bit x 256)..."
create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 \
    -module_name blk_mem_gen_1

set_property -dict [list \
    CONFIG.Memory_Type {True_Dual_Port_RAM} \
    CONFIG.Write_Width_A {64} \
    CONFIG.Write_Depth_A {256} \
    CONFIG.Read_Width_A {64} \
    CONFIG.Write_Width_B {64} \
    CONFIG.Read_Width_B {64} \
    CONFIG.Enable_A {Use_ENA_Pin} \
    CONFIG.Enable_B {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {true} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {true} \
    CONFIG.Use_Byte_Write_Enable {false} \
    CONFIG.Byte_Size {9} \
    CONFIG.Operating_Mode_A {WRITE_FIRST} \
    CONFIG.Operating_Mode_B {WRITE_FIRST} \
] [get_ips blk_mem_gen_1]

generate_target all [get_ips blk_mem_gen_1]
export_ip_user_files -of_objects [get_ips blk_mem_gen_1] -no_script -force

puts "  BRAM IPs created successfully."

################################################################################
# Step 4: Set top module
################################################################################
puts "\n>>> Step 4: Setting top module to mem_top..."
set_property top mem_top [current_fileset]
update_compile_order -fileset sources_1

################################################################################
# Step 5: Package IP
################################################################################
puts "\n>>> Step 5: Packaging IP..."

set ip_out_dir [file join $repo_out "${ip_name}_${ip_version}"]
file mkdir $ip_out_dir

ipx::package_project -root_dir $ip_out_dir -vendor $ip_vendor -library $ip_library \
    -taxonomy /UserIP -import_files -set_current true

set core [ipx::current_core]

set_property name $ip_name $core
set_property version $ip_version $core
set_property display_name "Memory Subsystem" $core
set_property description "Memory subsystem with AXI-Lite, AXI-Stream, AXI4-Full interfaces" $core
set_property vendor_display_name "MiniTPU" $core

################################################################################
# Step 6: Verify AXI interfaces
################################################################################
puts "\n>>> Step 6: Verifying AXI interfaces..."

puts "  Auto-inferred bus interfaces:"
foreach intf [ipx::get_bus_interfaces -of_objects $core] {
    set intf_name [get_property NAME $intf]
    set intf_mode [get_property INTERFACE_MODE $intf]
    set intf_vlnv [get_property ABSTRACTION_TYPE_VLNV $intf]
    puts "    - $intf_name ($intf_mode) : $intf_vlnv"
}

set required_intfs {s00_axi s00_axis m00_axis s01_axi}
foreach req_intf $required_intfs {
    if {[llength [ipx::get_bus_interfaces $req_intf -of_objects $core -quiet]] == 0} {
        puts "WARNING: Expected interface '$req_intf' not found!"
    } else {
        puts "  OK: Interface '$req_intf' found"
    }
}

################################################################################
# Step 7: Memory maps
################################################################################
puts "\n>>> Step 7: Adding memory maps..."

# AXI-Lite memory map (control registers)
set axi_lite_intf [ipx::get_bus_interfaces s00_axi -of_objects $core]
if {[llength [ipx::get_memory_maps s00_axi -of_objects $core -quiet]] == 0} {
    ipx::add_memory_map s00_axi $core
    set_property slave_memory_map_ref s00_axi $axi_lite_intf
    ipx::add_address_block reg0 [ipx::get_memory_maps s00_axi -of_objects $core]
    set addr_block [ipx::get_address_blocks reg0 -of_objects [ipx::get_memory_maps s00_axi -of_objects $core]]
    set_property range 64 $addr_block
    set_property width 32 $addr_block
    puts "  Added AXI-Lite memory map: 64 bytes"
}

# AXI4-Full memory map (system memory MMIO)
set axi_full_intf [ipx::get_bus_interfaces s01_axi -of_objects $core -quiet]
if {[llength $axi_full_intf] > 0} {
    if {[llength [ipx::get_memory_maps s01_axi -of_objects $core -quiet]] == 0} {
        ipx::add_memory_map s01_axi $core
        set_property slave_memory_map_ref s01_axi $axi_full_intf
        ipx::add_address_block mem0 [ipx::get_memory_maps s01_axi -of_objects $core]
        set addr_block [ipx::get_address_blocks mem0 -of_objects [ipx::get_memory_maps s01_axi -of_objects $core]]
        set_property range 262144 $addr_block
        set_property width 32 $addr_block
        puts "  Added AXI4-Full memory map: 256KB"
    }
}

################################################################################
# Step 8: Finalize
################################################################################
puts "\n>>> Step 8: Finalizing IP package..."

catch {set_property display_name "S00_AXI" [ipx::get_bus_interfaces s00_axi -of_objects $core]}
catch {set_property display_name "S00_AXIS" [ipx::get_bus_interfaces s00_axis -of_objects $core]}
catch {set_property display_name "M00_AXIS" [ipx::get_bus_interfaces m00_axis -of_objects $core]}
catch {set_property display_name "S01_AXI" [ipx::get_bus_interfaces s01_axi -of_objects $core]}

ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity $core
ipx::save_core $core

close_project
file delete -force $proj_dir

set vlnv "${ip_vendor}:${ip_library}:${ip_name}:${ip_version}"

puts ""
puts "============================================================"
puts "IP PACKAGING COMPLETE"
puts "============================================================"
puts "IP Location: $ip_out_dir"
puts "VLNV:        $vlnv"
puts "============================================================"

exit 0
