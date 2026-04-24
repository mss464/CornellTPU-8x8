################################################################################
# build_bd_bitstream.tcl
#
# Creates a Block Design with:
#   - Zynq UltraScale+ MPSoC (PS)
#   - AXI DMA (MM2S + S2MM)
#   - Cornell TPU IP
#   - Required interconnects, clocks, and resets
#
# Then builds synthesis, implementation, and generates bitstream.
#
# Usage:
#   vivado -mode batch -source scripts/build_bd_bitstream.tcl -tclargs \
#       -proj_name tpu_system \
#       -part xczu3eg-sbva484-1-i \
#       -ip_repo_path ip_repo \
#       -out_dir output
################################################################################

# Default values
set proj_name    "tpu_system"
set part         "xczu3eg-sbva484-1-i"
set ip_repo_path ""
set out_dir      ""
set bd_name      "tpu_bd"

# Parse command line arguments
proc parse_args {} {
    global argc argv
    global proj_name part ip_repo_path out_dir bd_name

    for {set i 0} {$i < $argc} {incr i} {
        set arg [lindex $argv $i]
        switch -exact -- $arg {
            "-proj_name" {
                incr i
                set proj_name [lindex $argv $i]
            }
            "-part" {
                incr i
                set part [lindex $argv $i]
            }
            "-ip_repo_path" {
                incr i
                set ip_repo_path [lindex $argv $i]
            }
            "-out_dir" {
                incr i
                set out_dir [lindex $argv $i]
            }
            "-bd_name" {
                incr i
                set bd_name [lindex $argv $i]
            }
            "-help" {
                puts "Usage: vivado -mode batch -source build_bd_bitstream.tcl -tclargs <options>"
                puts "Options:"
                puts "  -proj_name <name>       Project name (default: tpu_system)"
                puts "  -part <part>            FPGA part number (default: xczu3eg-sbva484-1-i)"
                puts "  -ip_repo_path <path>    Path to IP repository containing TPU IP"
                puts "  -out_dir <dir>          Output directory for bitstream and reports"
                puts "  -bd_name <name>         Block design name (default: tpu_bd)"
                puts "  -help                   Show this help message"
                exit 0
            }
            default {
                puts "WARNING: Unknown argument: $arg"
            }
        }
    }

    # Validate required arguments
    if {$ip_repo_path eq ""} {
        puts "ERROR: -ip_repo_path is required"
        exit 1
    }
    if {$out_dir eq ""} {
        puts "ERROR: -out_dir is required"
        exit 1
    }
}

parse_args

# Convert to absolute paths
set ip_repo_path [file normalize $ip_repo_path]
set out_dir [file normalize $out_dir]

puts "============================================================"
puts "TPU Block Design & Bitstream Build Script"
puts "============================================================"
puts "Project:     $proj_name"
puts "Part:        $part"
puts "IP Repo:     $ip_repo_path"
puts "Output Dir:  $out_dir"
puts "BD Name:     $bd_name"
puts "============================================================"

# Create output directories
set proj_dir [file join $out_dir $proj_name]
set artifacts_dir [file join $out_dir "artifacts"]
file mkdir $out_dir
file mkdir $artifacts_dir

################################################################################
# Step 1: Create Project
################################################################################
puts "\n>>> Step 1: Creating project..."
file delete -force $proj_dir
create_project $proj_name $proj_dir -part $part -force

# Define TARGET_FPGA for conditional compilation (selects Xilinx BRAM IPs)
set_property verilog_define {TARGET_FPGA=1} [current_fileset]

################################################################################
# Step 2: Add IP Repository
################################################################################
puts "\n>>> Step 2: Adding IP repository..."
set_property ip_repo_paths $ip_repo_path [current_project]
update_ip_catalog -rebuild

# Verify TPU IP is available
set tpu_ip [get_ipdefs -filter "NAME =~ *cornell_tpu*"]
if {$tpu_ip eq ""} {
    # Try alternative search
    set tpu_ip [get_ipdefs -filter "NAME =~ *tpu*"]
}
if {$tpu_ip eq ""} {
    puts "ERROR: TPU IP not found in repository: $ip_repo_path"
    puts "Available IPs:"
    foreach ip [get_ipdefs] {
        puts "  $ip"
    }
    close_project
    exit 1
}
puts "  Found TPU IP: $tpu_ip"

################################################################################
# Step 3: Create Block Design
################################################################################
puts "\n>>> Step 3: Creating block design..."
create_bd_design $bd_name

################################################################################
# Step 4: Add Zynq UltraScale+ MPSoC
################################################################################
puts "\n>>> Step 4: Adding Zynq UltraScale+ MPSoC..."
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 zynq_ps]

# Configure PS with basic settings
# Enable one master AXI port and one slave HP port
# Note: S_AXI_GP2 maps to S_AXI_HP0_FPD, S_AXI_GP0 is HPC0
set_property -dict [list \
    CONFIG.PSU__USE__M_AXI_GP0 {0} \
    CONFIG.PSU__USE__M_AXI_GP1 {0} \
    CONFIG.PSU__USE__M_AXI_GP2 {1} \
    CONFIG.PSU__USE__S_AXI_GP0 {0} \
    CONFIG.PSU__USE__S_AXI_GP2 {1} \
    CONFIG.PSU__USE__S_AXI_GP3 {0} \
    CONFIG.PSU__USE__S_AXI_GP4 {0} \
    CONFIG.PSU__USE__S_AXI_GP5 {0} \
    CONFIG.PSU__USE__S_AXI_GP6 {0} \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {50} \
] $ps

################################################################################
# Step 5: Add Processor System Reset
################################################################################
puts "\n>>> Step 5: Adding Processor System Reset..."
set ps_reset [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 proc_sys_reset_0]

################################################################################
# Step 6: Add AXI DMA
################################################################################
puts "\n>>> Step 6: Adding AXI DMA..."
set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0]

# Configure DMA for both MM2S and S2MM
# MM2S: Memory to Stream (input to TPU) - 64-bit width
# S2MM: Stream to Memory (output from TPU) - 32-bit width
set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_include_stscntrl_strm {0} \
    CONFIG.c_include_mm2s {1} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_mm2s_burst_size {16} \
    CONFIG.c_s2mm_burst_size {16} \
    CONFIG.c_m_axi_mm2s_data_width {64} \
    CONFIG.c_m_axis_mm2s_tdata_width {64} \
    CONFIG.c_m_axi_s2mm_data_width {32} \
    CONFIG.c_s_axis_s2mm_tdata_width {32} \
] $dma

################################################################################
# Step 7: Add TPU IP
################################################################################
puts "\n>>> Step 7: Adding TPU IP..."
set tpu [create_bd_cell -type ip -vlnv $tpu_ip tpu_0]

################################################################################
# Step 8: Add AXI Interconnect for Control Path
################################################################################
puts "\n>>> Step 8: Adding AXI Interconnect..."

# AXI Interconnect for control path (PS -> TPU AXI-Lite, DMA control)
set axi_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_interconnect_0]
set_property -dict [list \
    CONFIG.NUM_MI {2} \
    CONFIG.NUM_SI {1} \
] $axi_ic

################################################################################
# Step 9: Add AXI SmartConnect for DMA Memory Access
################################################################################
puts "\n>>> Step 9: Adding AXI SmartConnect for DMA..."
set axi_sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_smc]
set_property -dict [list \
    CONFIG.NUM_SI {2} \
    CONFIG.NUM_MI {1} \
] $axi_sc

################################################################################
# Step 10: Connect AXI Interfaces First (creates dynamic pins)
################################################################################
puts "\n>>> Step 10: Connecting AXI control path..."
# PS Master -> Interconnect
connect_bd_intf_net [get_bd_intf_pins zynq_ps/M_AXI_HPM0_LPD] \
                    [get_bd_intf_pins axi_interconnect_0/S00_AXI]

# Interconnect -> DMA Control
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] \
                    [get_bd_intf_pins axi_dma_0/S_AXI_LITE]

# Interconnect -> TPU AXI-Lite
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M01_AXI] \
                    [get_bd_intf_pins tpu_0/s00_axi]

################################################################################
# Step 11: Connect AXI-Stream Data Path
################################################################################
puts "\n>>> Step 11: Connecting AXI-Stream data path..."

# DMA MM2S -> TPU Input Stream (64-bit)
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] \
                    [get_bd_intf_pins tpu_0/s00_axis]

# TPU Output Stream -> DMA S2MM (32-bit)
connect_bd_intf_net [get_bd_intf_pins tpu_0/m00_axis] \
                    [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]

################################################################################
# Step 12: Connect DMA Memory Interfaces
################################################################################
puts "\n>>> Step 12: Connecting DMA memory interfaces..."

# DMA AXI memory ports -> SmartConnect
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] \
                    [get_bd_intf_pins axi_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] \
                    [get_bd_intf_pins axi_smc/S01_AXI]

# SmartConnect -> PS HP0
connect_bd_intf_net [get_bd_intf_pins axi_smc/M00_AXI] \
                    [get_bd_intf_pins zynq_ps/S_AXI_HP0_FPD]

################################################################################
# Step 13: Connect Clocks (after interfaces are connected)
################################################################################
puts "\n>>> Step 13: Connecting clocks..."

# PS PL clock
set pl_clk [get_bd_pins zynq_ps/pl_clk0]

# Connect all clocks to PL clock
connect_bd_net $pl_clk [get_bd_pins proc_sys_reset_0/slowest_sync_clk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/s_axi_lite_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/m_axi_mm2s_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/m_axi_s2mm_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/S00_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/M00_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/M01_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_smc/aclk]
connect_bd_net $pl_clk [get_bd_pins zynq_ps/maxihpm0_lpd_aclk]
connect_bd_net $pl_clk [get_bd_pins zynq_ps/saxihp0_fpd_aclk]

# Connect TPU clocks (all from same source)
connect_bd_net $pl_clk [get_bd_pins tpu_0/s00_axi_aclk]
connect_bd_net $pl_clk [get_bd_pins tpu_0/s00_axis_aclk]
connect_bd_net $pl_clk [get_bd_pins tpu_0/m00_axis_aclk]

################################################################################
# Step 14: Connect Resets
################################################################################
puts "\n>>> Step 14: Connecting resets..."

# PS reset output
connect_bd_net [get_bd_pins zynq_ps/pl_resetn0] [get_bd_pins proc_sys_reset_0/ext_reset_in]

# Interconnect reset (active low)
set ic_resetn [get_bd_pins proc_sys_reset_0/interconnect_aresetn]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/S00_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/M00_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/M01_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_smc/aresetn]

# Peripheral reset (active low)
set periph_resetn [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
connect_bd_net $periph_resetn [get_bd_pins axi_dma_0/axi_resetn]
connect_bd_net $periph_resetn [get_bd_pins tpu_0/s00_axi_aresetn]
connect_bd_net $periph_resetn [get_bd_pins tpu_0/s00_axis_aresetn]
connect_bd_net $periph_resetn [get_bd_pins tpu_0/m00_axis_aresetn]

################################################################################
# Step 15: Assign Addresses
################################################################################
puts "\n>>> Step 15: Assigning addresses..."

# Assign all addresses automatically
assign_bd_address -target_address_space /zynq_ps/Data [get_bd_addr_segs axi_dma_0/S_AXI_LITE/Reg] -force
assign_bd_address -target_address_space /zynq_ps/Data [get_bd_addr_segs tpu_0/s00_axi/reg0] -force

# Assign DMA address spaces
assign_bd_address -target_address_space /axi_dma_0/Data_MM2S [get_bd_addr_segs zynq_ps/SAXIGP2/HP0_DDR_LOW] -force
assign_bd_address -target_address_space /axi_dma_0/Data_S2MM [get_bd_addr_segs zynq_ps/SAXIGP2/HP0_DDR_LOW] -force

# Print address map
puts "\n  Address Map:"
foreach seg [get_bd_addr_segs] {
    if {[get_property OFFSET $seg] ne ""} {
        set offset [format "0x%08X" [get_property OFFSET $seg]]
        set range [format "0x%08X" [get_property RANGE $seg]]
        puts "    [get_property PATH $seg]: Offset=$offset, Range=$range"
    }
}

################################################################################
# Step 16: Validate Block Design
################################################################################
puts "\n>>> Step 16: Validating block design..."
validate_bd_design
save_bd_design

################################################################################
# Step 17: Generate Output Products
################################################################################
puts "\n>>> Step 17: Generating output products..."
generate_target all [get_files [file join $proj_dir $proj_name.srcs sources_1 bd $bd_name $bd_name.bd]]

################################################################################
# Step 18: Create HDL Wrapper
################################################################################
puts "\n>>> Step 18: Creating HDL wrapper..."
set bd_file [get_files [file join $proj_dir $proj_name.srcs sources_1 bd $bd_name $bd_name.bd]]
set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top ${bd_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

################################################################################
# Step 19: Run Synthesis
################################################################################
puts "\n>>> Step 19: Running synthesis..."
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1

# Check synthesis status
set synth_status [get_property STATUS [get_runs synth_1]]
puts "  Synthesis status: $synth_status"
if {$synth_status ne "synth_design Complete!"} {
    puts "ERROR: Synthesis failed"
    close_project
    exit 1
}

################################################################################
# Step 20: Run Implementation
################################################################################
puts "\n>>> Step 20: Running implementation..."
launch_runs impl_1 -jobs 4
wait_on_run impl_1

# Check implementation status
set impl_status [get_property STATUS [get_runs impl_1]]
puts "  Implementation status: $impl_status"
if {[string match "*ERROR*" $impl_status]} {
    puts "ERROR: Implementation failed"
    close_project
    exit 1
}

################################################################################
# Step 21: Generate Bitstream
################################################################################
puts "\n>>> Step 21: Generating bitstream..."
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1

################################################################################
# Step 22: Export Artifacts
################################################################################
puts "\n>>> Step 22: Exporting artifacts..."

# Find and copy bitstream
set bit_file [glob -nocomplain [file join $proj_dir $proj_name.runs impl_1 *.bit]]
if {$bit_file ne ""} {
    set dest_bit [file join $artifacts_dir "${bd_name}.bit"]
    file copy -force $bit_file $dest_bit
    puts "  Bitstream: $dest_bit"
} else {
    puts "WARNING: Bitstream not found"
}

# Find and copy hardware handoff (for SDK/Vitis)
set hwh_file [glob -nocomplain [file join $proj_dir $proj_name.gen sources_1 bd $bd_name hw_handoff *.hwh]]
if {$hwh_file ne ""} {
    set dest_hwh [file join $artifacts_dir "${bd_name}.hwh"]
    file copy -force $hwh_file $dest_hwh
    puts "  Hardware handoff: $dest_hwh"
}

# Export utilization report
open_run impl_1
set util_file [file join $artifacts_dir "utilization_report.txt"]
report_utilization -file $util_file
puts "  Utilization report: $util_file"

# Export timing summary report
set timing_file [file join $artifacts_dir "timing_summary.txt"]
report_timing_summary -file $timing_file
puts "  Timing summary: $timing_file"

# Export power report
set power_file [file join $artifacts_dir "power_report.txt"]
report_power -file $power_file
puts "  Power report: $power_file"

################################################################################
# Done
################################################################################
close_project

puts ""
puts "============================================================"
puts "BUILD COMPLETE"
puts "============================================================"
puts "Artifacts directory: $artifacts_dir"
puts ""
puts "Files:"
foreach f [glob -nocomplain [file join $artifacts_dir *]] {
    puts "  [file tail $f]"
}
puts "============================================================"

exit 0