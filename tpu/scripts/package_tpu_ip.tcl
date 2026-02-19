################################################################################
# package_tpu_ip.tcl
#
# Packages the tpu RTL into a reusable custom IP with:
#   - AXI4-Lite slave interface (s00_axi)
#   - AXI-Stream slave interface (s00_axis)
#   - AXI-Stream master interface (m00_axis)
#   - Embedded blk_mem_gen_1 BRAM IP (generated locally to avoid black-box)
#
# Usage:
#   vivado -mode batch -source scripts/package_tpu_ip.tcl -tclargs \
#       -ip_name mini_tpu \
#       -part xczu3eg-sbva484-1-i \
#       -rtl_dir tpu \
#       -repo_out ip_repo
################################################################################

# Default values
set ip_name     "mini_tpu"
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
                puts "Usage: vivado -mode batch -source package_tpu_ip.tcl -tclargs <options>"
                puts "Options:"
                puts "  -ip_name <name>      IP core name (default: mini_tpu)"
                puts "  -part <part>         FPGA part number (default: xczu3eg-sbva484-1-i)"
                puts "  -rtl_dir <dir>       Directory containing RTL sources (can specify multiple)"
                puts "  -repo_out <dir>      Output directory for IP repository"
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

    # Validate required arguments
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

# Convert to absolute paths
set normalized_dirs {}
foreach d $rtl_dirs {
    lappend normalized_dirs [file normalize $d]
}
set rtl_dirs $normalized_dirs
set repo_out [file normalize $repo_out]

puts "============================================================"
puts "TPU IP Packaging Script"
puts "============================================================"
puts "IP Name:     $ip_name"
puts "IP Version:  $ip_version"
puts "Part:        $part"
puts "RTL Dirs:    $rtl_dirs"
puts "Output Repo: $repo_out"
puts "============================================================"

# Create output directory
file mkdir $repo_out

# Create temporary project directory
set proj_dir [file join [pwd] "pkg_${ip_name}_proj"]
file delete -force $proj_dir

################################################################################
# Step 1: Create Project
################################################################################
puts "\n>>> Step 1: Creating project..."
create_project pkg_${ip_name} $proj_dir -part $part -force
set_property target_language Verilog [current_project]



################################################################################
# Step 2: Add RTL Files
################################################################################
puts "\n>>> Step 2: Adding RTL files..."

# Find all Verilog files from all RTL directories
set v_files {}
set sv_files {}
foreach rtl_dir $rtl_dirs {
    puts "  Scanning: $rtl_dir"
    set v_files [concat $v_files [glob -nocomplain -directory $rtl_dir *.v]]
    set sv_files [concat $sv_files [glob -nocomplain -directory $rtl_dir *.sv]]
}
set all_rtl_files [concat $v_files $sv_files]

if {[llength $all_rtl_files] == 0} {
    puts "ERROR: No RTL files found in: $rtl_dirs"
    close_project
    exit 1
}

foreach f $all_rtl_files {
    puts "  Adding: [file tail $f]"
    add_files -norecurse $f
}

# Set file types explicitly
foreach f $sv_files {
    set_property file_type "SystemVerilog" [get_files $f]
}

################################################################################
# Step 3: Create BRAM IPs
################################################################################
puts "\n>>> Step 3: Creating BRAM IPs..."

# --- blk_mem_gen_0: Data BRAM used in scratchpad.sv ---
# 32-bit wide, 8192 deep (13-bit address), True Dual Port RAM
puts "  Creating blk_mem_gen_0 (Data BRAM - 32-bit x 8192)..."

create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 \
    -module_name blk_mem_gen_0

set_property -dict [list \
    CONFIG.Memory_Type {True_Dual_Port_RAM} \
    CONFIG.Write_Width_A {32} \
    CONFIG.Write_Depth_A {8192} \
    CONFIG.Read_Width_A {32} \
    CONFIG.Write_Width_B {32} \
    CONFIG.Read_Width_B {32} \
    CONFIG.Enable_A {Use_ENA_Pin} \
    CONFIG.Enable_B {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {true} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {true} \
    CONFIG.Use_Byte_Write_Enable {false} \
    CONFIG.Byte_Size {9} \
    CONFIG.Operating_Mode_A {WRITE_FIRST} \
    CONFIG.Operating_Mode_B {WRITE_FIRST} \
] [get_ips blk_mem_gen_0]

generate_target all [get_ips blk_mem_gen_0]
export_ip_user_files -of_objects [get_ips blk_mem_gen_0] -no_script -force

# --- blk_mem_gen_1: Instruction BRAM used in tpu.sv ---
# 64-bit wide, 256 deep (8-bit address), True Dual Port RAM
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

puts "  BRAM IPs created and targets generated."

################################################################################
# Step 4: Set Top Module
################################################################################
puts "\n>>> Step 4: Setting top module to tpu..."
set_property top tpu [current_fileset]
update_compile_order -fileset sources_1

################################################################################
# Step 5: Package IP
################################################################################
puts "\n>>> Step 5: Packaging IP..."

# Set IP output location
set ip_out_dir [file join $repo_out "${ip_name}_${ip_version}"]
file mkdir $ip_out_dir

# Package the project - Vivado will auto-infer AXI interfaces
ipx::package_project -root_dir $ip_out_dir -vendor $ip_vendor -library $ip_library \
    -taxonomy /UserIP -import_files -set_current true

# Get the current IP core
set core [ipx::current_core]

# Set IP properties
set_property name $ip_name $core
set_property version $ip_version $core
set_property display_name "Mini-TPU Accelerator" $core
set_property description "TPU accelerator with AXI-Lite control and AXI-Stream data interfaces" $core
set_property vendor_display_name "Mini-TPU" $core
set_property company_url "https://github.com/sunwookim028/CornellTPU" $core



################################################################################
# Step 6: Verify Auto-Inferred AXI Interfaces
################################################################################
puts "\n>>> Step 6: Verifying auto-inferred AXI interfaces..."

# List all bus interfaces that were auto-inferred
puts "  Auto-inferred bus interfaces:"
foreach intf [ipx::get_bus_interfaces -of_objects $core] {
    set intf_name [get_property NAME $intf]
    set intf_mode [get_property INTERFACE_MODE $intf]
    set intf_vlnv [get_property ABSTRACTION_TYPE_VLNV $intf]
    puts "    - $intf_name ($intf_mode) : $intf_vlnv"
}

# Verify the expected interfaces exist (using lowercase names as Vivado infers)
set required_intfs {s00_axi s00_axis m00_axis}
foreach req_intf $required_intfs {
    if {[llength [ipx::get_bus_interfaces $req_intf -of_objects $core -quiet]] == 0} {
        puts "WARNING: Expected interface '$req_intf' not found!"
    } else {
        puts "  OK: Interface '$req_intf' found"
    }
}

################################################################################
# Step 7: Add Memory Map for AXI-Lite Interface
################################################################################
puts "\n>>> Step 7: Adding memory map for AXI-Lite interface..."

# Get the AXI-Lite interface (lowercase as auto-inferred by Vivado)
set axi_lite_intf [ipx::get_bus_interfaces s00_axi -of_objects $core]

# Check if memory map already exists
if {[llength [ipx::get_memory_maps s00_axi -of_objects $core -quiet]] == 0} {
    # Create memory map for register space (6-bit address = 64 bytes)
    ipx::add_memory_map s00_axi $core
    set_property slave_memory_map_ref s00_axi $axi_lite_intf
    
    ipx::add_address_block reg0 [ipx::get_memory_maps s00_axi -of_objects $core]
    set addr_block [ipx::get_address_blocks reg0 -of_objects [ipx::get_memory_maps s00_axi -of_objects $core]]
    set_property range 64 $addr_block
    set_property width 32 $addr_block
    puts "  Added memory map: 64 bytes, 32-bit width"
} else {
    puts "  Memory map already exists"
}

################################################################################
# Step 8: Set Interface Display Names (optional, for cleaner BD view)
################################################################################
puts "\n>>> Step 8: Setting interface display names..."

# Rename interfaces to uppercase for cleaner block design appearance
catch {set_property display_name "S00_AXI" [ipx::get_bus_interfaces s00_axi -of_objects $core]}
catch {set_property display_name "S00_AXIS" [ipx::get_bus_interfaces s00_axis -of_objects $core]}
catch {set_property display_name "M00_AXIS" [ipx::get_bus_interfaces m00_axis -of_objects $core]}

################################################################################
# Step 9: Finalize and Save
################################################################################
puts "\n>>> Step 9: Finalizing IP package..."

# Update checksums and validate
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity $core
ipx::save_core $core

# Close packaging project
close_project

# Cleanup temporary project
file delete -force $proj_dir

################################################################################
# Done
################################################################################
set vlnv "${ip_vendor}:${ip_library}:${ip_name}:${ip_version}"

puts ""
puts "============================================================"
puts "IP PACKAGING COMPLETE"
puts "============================================================"
puts "IP Location: $ip_out_dir"
puts "VLNV:        $vlnv"
puts "============================================================"
puts ""
puts "To use this IP in a Vivado project:"
puts "  set_property ip_repo_paths $repo_out \[current_project\]"
puts "  update_ip_catalog"
puts ""

exit 0
