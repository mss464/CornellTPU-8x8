################################################################################
# build_mem_bitstream.tcl
#
# Creates a Block Design with:
#   - Zynq UltraScale+ MPSoC (PS)
#   - AXI DMA (MM2S + S2MM) — bulk transfers
#   - Memory Subsystem IP (mem_top)
#   - Required interconnects, clocks, and resets
#
# The mem_top IP exposes four AXI interfaces:
#   s00_axi  — AXI-Lite control registers (from PS via interconnect)
#   s00_axis — AXI-Stream slave (from DMA MM2S)
#   m00_axis — AXI-Stream master (to DMA S2MM)
#   s01_axi  — AXI4-Full slave (from PS for direct MMIO)
#
# Then builds synthesis, implementation, and generates bitstream.
#
# Usage:
#   vivado -mode batch -source scripts/build_mem_bitstream.tcl -tclargs \
#       -proj_name mem_system \
#       -part xczu3eg-sbva484-1-i \
#       -ip_repo_path ip_repo \
#       -out_dir build
################################################################################

# Default values
set proj_name    "mem_system"
set part         "xczu3eg-sbva484-1-i"
set ip_repo_path ""
set out_dir      ""
set bd_name      "mem_bd"

proc parse_args {} {
    global argc argv
    global proj_name part ip_repo_path out_dir bd_name

    for {set i 0} {$i < $argc} {incr i} {
        set arg [lindex $argv $i]
        switch -exact -- $arg {
            "-proj_name" { incr i; set proj_name [lindex $argv $i] }
            "-part"      { incr i; set part [lindex $argv $i] }
            "-ip_repo_path" { incr i; set ip_repo_path [lindex $argv $i] }
            "-out_dir"   { incr i; set out_dir [lindex $argv $i] }
            "-bd_name"   { incr i; set bd_name [lindex $argv $i] }
            "-help" {
                puts "Usage: vivado -mode batch -source build_mem_bitstream.tcl -tclargs <options>"
                puts "  -proj_name <name>       Project name"
                puts "  -part <part>            FPGA part number"
                puts "  -ip_repo_path <path>    IP repository path"
                puts "  -out_dir <dir>          Output directory"
                puts "  -bd_name <name>         Block design name"
                exit 0
            }
            default { puts "WARNING: Unknown argument: $arg" }
        }
    }

    if {$ip_repo_path eq ""} { puts "ERROR: -ip_repo_path required"; exit 1 }
    if {$out_dir eq ""}      { puts "ERROR: -out_dir required"; exit 1 }
}

parse_args

set ip_repo_path [file normalize $ip_repo_path]
set out_dir [file normalize $out_dir]

puts "============================================================"
puts "Memory Subsystem Block Design & Bitstream Build"
puts "============================================================"
puts "Project:     $proj_name"
puts "Part:        $part"
puts "IP Repo:     $ip_repo_path"
puts "Output Dir:  $out_dir"
puts "BD Name:     $bd_name"
puts "============================================================"

set proj_dir [file join $out_dir $proj_name]
set artifacts_dir [file join $out_dir "artifacts"]
file mkdir $out_dir
file mkdir $artifacts_dir

################################################################################
# Step 1: Create Project
################################################################################
puts "\n>>> Step 1: Creating project..."
if {[file exists $proj_dir]} {
    # Try clean delete first; if NFS stale handles block it, rename out of the way
    if {[catch {file delete -force $proj_dir}]} {
        set stale_dir "${proj_dir}_stale_[clock seconds]"
        puts "  WARNING: Cannot delete $proj_dir (NFS stale handles), renaming to $stale_dir"
        catch {file rename -force $proj_dir $stale_dir}
    }
}
create_project $proj_name $proj_dir -part $part -force
set_property verilog_define {TARGET_FPGA=1} [current_fileset]

################################################################################
# Step 2: Add IP Repository
################################################################################
puts "\n>>> Step 2: Adding IP repository..."
set_property ip_repo_paths $ip_repo_path [current_project]
update_ip_catalog -rebuild

set mem_ip [get_ipdefs -filter "NAME =~ *mem_subsys*"]
if {$mem_ip eq ""} {
    set mem_ip [get_ipdefs -filter "NAME =~ *mem*"]
}
if {$mem_ip eq ""} {
    puts "ERROR: Memory subsystem IP not found in: $ip_repo_path"
    foreach ip [get_ipdefs] { puts "  $ip" }
    close_project
    exit 1
}
puts "  Found Memory IP: $mem_ip"

################################################################################
# Step 3: Create Block Design
################################################################################
puts "\n>>> Step 3: Creating block design..."
create_bd_design $bd_name

################################################################################
# Step 4: Add Zynq PS
################################################################################
puts "\n>>> Step 4: Adding Zynq UltraScale+ MPSoC..."
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 zynq_ps]

# Enable:
#   M_AXI_HPM0_LPD  — PS master for AXI-Lite control + DMA control
#   M_AXI_HPM0_FPD  — PS master for AXI4-Full direct MMIO to sys_mem
#   S_AXI_HP0_FPD   — PS slave for DMA memory access
set_property -dict [list \
    CONFIG.PSU__USE__M_AXI_GP0 {1} \
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
set_property -dict [list CONFIG.C_EXT_RESET_HIGH {0}] $ps_reset

################################################################################
# Step 6: Add AXI DMA
################################################################################
puts "\n>>> Step 6: Adding AXI DMA..."
set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0]

set_property -dict [list \
    CONFIG.c_include_sg {0} \
    CONFIG.c_sg_include_stscntrl_strm {0} \
    CONFIG.c_sg_length_width {26} \
    CONFIG.c_include_mm2s {1} \
    CONFIG.c_include_s2mm {1} \
    CONFIG.c_mm2s_burst_size {16} \
    CONFIG.c_s2mm_burst_size {16} \
    CONFIG.c_m_axi_mm2s_data_width {256} \
    CONFIG.c_m_axis_mm2s_tdata_width {256} \
    CONFIG.c_m_axi_s2mm_data_width {256} \
    CONFIG.c_s_axis_s2mm_tdata_width {256} \
] $dma

################################################################################
# Step 7: Add Memory Subsystem IP
################################################################################
puts "\n>>> Step 7: Adding Memory Subsystem IP..."
set mem [create_bd_cell -type ip -vlnv $mem_ip mem_top_0]

################################################################################
# Step 8: Add AXI Interconnect for Control Path (PS LPD → Lite + DMA ctrl)
################################################################################
puts "\n>>> Step 8: Adding AXI Interconnect for control..."
set axi_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_interconnect_0]
set_property -dict [list \
    CONFIG.NUM_MI {2} \
    CONFIG.NUM_SI {1} \
] $axi_ic

################################################################################
# Step 9: Add SmartConnect for DMA Memory Access
################################################################################
puts "\n>>> Step 9: Adding SmartConnect for DMA..."
set axi_sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_smc]
set_property -dict [list \
    CONFIG.NUM_SI {2} \
    CONFIG.NUM_MI {1} \
] $axi_sc

################################################################################
# Step 10: Connect AXI Control Path
################################################################################
puts "\n>>> Step 10: Connecting AXI control path..."

# PS LPD Master → Interconnect → DMA ctrl + mem_top AXI-Lite
connect_bd_intf_net [get_bd_intf_pins zynq_ps/M_AXI_HPM0_LPD] \
                    [get_bd_intf_pins axi_interconnect_0/S00_AXI]

connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] \
                    [get_bd_intf_pins axi_dma_0/S_AXI_LITE]

connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M01_AXI] \
                    [get_bd_intf_pins mem_top_0/s00_axi]

################################################################################
# Step 11: Connect AXI4-Full (PS FPD Master → mem_top s01_axi)
################################################################################
puts "\n>>> Step 11: Connecting AXI4-Full MMIO path..."

# PS FPD Master → mem_top AXI4-Full slave (direct connection via SmartConnect)
set axi_sc_full [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_smc_full]
set_property -dict [list \
    CONFIG.NUM_SI {1} \
    CONFIG.NUM_MI {1} \
] $axi_sc_full

connect_bd_intf_net [get_bd_intf_pins zynq_ps/M_AXI_HPM0_FPD] \
                    [get_bd_intf_pins axi_smc_full/S00_AXI]

connect_bd_intf_net [get_bd_intf_pins axi_smc_full/M00_AXI] \
                    [get_bd_intf_pins mem_top_0/s01_axi]

################################################################################
# Step 12: Connect AXI-Stream Data Path
################################################################################
puts "\n>>> Step 12: Connecting AXI-Stream data path..."

connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] \
                    [get_bd_intf_pins mem_top_0/s00_axis]

connect_bd_intf_net [get_bd_intf_pins mem_top_0/m00_axis] \
                    [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]

# Re-assert DMA stream widths
set_property -dict [list \
    CONFIG.c_m_axi_mm2s_data_width {256} \
    CONFIG.c_m_axis_mm2s_tdata_width {256} \
    CONFIG.c_m_axi_s2mm_data_width {256} \
    CONFIG.c_s_axis_s2mm_tdata_width {256} \
] [get_bd_cells axi_dma_0]

################################################################################
# Step 13: Connect DMA Memory Interfaces
################################################################################
puts "\n>>> Step 13: Connecting DMA memory interfaces..."

connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] \
                    [get_bd_intf_pins axi_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] \
                    [get_bd_intf_pins axi_smc/S01_AXI]

connect_bd_intf_net [get_bd_intf_pins axi_smc/M00_AXI] \
                    [get_bd_intf_pins zynq_ps/S_AXI_HP0_FPD]

################################################################################
# Step 14: Connect Clocks
################################################################################
puts "\n>>> Step 14: Connecting clocks..."

set pl_clk [get_bd_pins zynq_ps/pl_clk0]

connect_bd_net $pl_clk [get_bd_pins proc_sys_reset_0/slowest_sync_clk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/s_axi_lite_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/m_axi_mm2s_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/m_axi_s2mm_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/S00_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/M00_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/M01_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_smc/aclk]
connect_bd_net $pl_clk [get_bd_pins axi_smc_full/aclk]
connect_bd_net $pl_clk [get_bd_pins zynq_ps/maxihpm0_lpd_aclk]
connect_bd_net $pl_clk [get_bd_pins zynq_ps/maxihpm0_fpd_aclk]
connect_bd_net $pl_clk [get_bd_pins zynq_ps/saxihp0_fpd_aclk]

# mem_top clocks
connect_bd_net $pl_clk [get_bd_pins mem_top_0/s00_axi_aclk]
connect_bd_net $pl_clk [get_bd_pins mem_top_0/s00_axis_aclk]
connect_bd_net $pl_clk [get_bd_pins mem_top_0/m00_axis_aclk]
connect_bd_net $pl_clk [get_bd_pins mem_top_0/s01_axi_aclk]

################################################################################
# Step 15: Connect Resets
################################################################################
puts "\n>>> Step 15: Connecting resets..."

connect_bd_net [get_bd_pins zynq_ps/pl_resetn0] [get_bd_pins proc_sys_reset_0/ext_reset_in]

set ic_resetn [get_bd_pins proc_sys_reset_0/interconnect_aresetn]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/S00_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/M00_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/M01_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_smc/aresetn]
connect_bd_net $ic_resetn [get_bd_pins axi_smc_full/aresetn]

set periph_resetn [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
connect_bd_net $periph_resetn [get_bd_pins axi_dma_0/axi_resetn]
connect_bd_net $periph_resetn [get_bd_pins mem_top_0/s00_axi_aresetn]
connect_bd_net $periph_resetn [get_bd_pins mem_top_0/s00_axis_aresetn]
connect_bd_net $periph_resetn [get_bd_pins mem_top_0/m00_axis_aresetn]
connect_bd_net $periph_resetn [get_bd_pins mem_top_0/s01_axi_aresetn]

################################################################################
# Step 16: Assign Addresses
################################################################################
puts "\n>>> Step 16: Assigning addresses..."

assign_bd_address -target_address_space /zynq_ps/Data [get_bd_addr_segs axi_dma_0/S_AXI_LITE/Reg] -force
assign_bd_address -target_address_space /zynq_ps/Data [get_bd_addr_segs mem_top_0/s00_axi/reg0] -force
assign_bd_address -target_address_space /zynq_ps/Data [get_bd_addr_segs mem_top_0/s01_axi/mem0] -force

assign_bd_address -target_address_space /axi_dma_0/Data_MM2S [get_bd_addr_segs zynq_ps/SAXIGP2/HP0_DDR_LOW] -force
assign_bd_address -target_address_space /axi_dma_0/Data_S2MM [get_bd_addr_segs zynq_ps/SAXIGP2/HP0_DDR_LOW] -force

puts "\n  Address Map:"
foreach seg [get_bd_addr_segs] {
    if {[get_property OFFSET $seg] ne ""} {
        set offset [format "0x%08X" [get_property OFFSET $seg]]
        set range [format "0x%08X" [get_property RANGE $seg]]
        puts "    [get_property PATH $seg]: Offset=$offset, Range=$range"
    }
}

################################################################################
# Step 17: Validate & Generate
################################################################################
puts "\n>>> Step 17: Validating block design..."
validate_bd_design
save_bd_design

puts "\n>>> Step 18: Generating output products..."
generate_target all [get_files [file join $proj_dir $proj_name.srcs sources_1 bd $bd_name $bd_name.bd]]

puts "\n>>> Step 19: Creating HDL wrapper..."
set bd_file [get_files [file join $proj_dir $proj_name.srcs sources_1 bd $bd_name $bd_name.bd]]
set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top ${bd_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

################################################################################
# Step 20: Synthesis
################################################################################
puts "\n>>> Step 20: Running synthesis..."
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1

set synth_status [get_property STATUS [get_runs synth_1]]
puts "  Synthesis status: $synth_status"
if {$synth_status ne "synth_design Complete!"} {
    puts "ERROR: Synthesis failed"
    close_project
    exit 1
}

################################################################################
# Step 21: Implementation
################################################################################
puts "\n>>> Step 21: Running implementation..."
launch_runs impl_1 -jobs 4
wait_on_run impl_1

set impl_status [get_property STATUS [get_runs impl_1]]
puts "  Implementation status: $impl_status"
if {[string match "*ERROR*" $impl_status]} {
    puts "ERROR: Implementation failed"
    close_project
    exit 1
}

################################################################################
# Step 22: Bitstream
################################################################################
puts "\n>>> Step 22: Generating bitstream..."
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1

################################################################################
# Step 23: Export Artifacts
################################################################################
puts "\n>>> Step 23: Exporting artifacts..."

set bit_file [glob -nocomplain [file join $proj_dir $proj_name.runs impl_1 *.bit]]
if {$bit_file ne ""} {
    set dest_bit [file join $artifacts_dir "${bd_name}.bit"]
    file copy -force $bit_file $dest_bit
    puts "  Bitstream: $dest_bit"
} else {
    puts "WARNING: Bitstream not found"
}

set hwh_file [glob -nocomplain [file join $proj_dir $proj_name.gen sources_1 bd $bd_name hw_handoff *.hwh]]
if {$hwh_file ne ""} {
    set dest_hwh [file join $artifacts_dir "${bd_name}.hwh"]
    file copy -force $hwh_file $dest_hwh
    puts "  Hardware handoff: $dest_hwh"
}

open_run impl_1
report_utilization -file [file join $artifacts_dir "utilization_report.txt"]
report_timing_summary -file [file join $artifacts_dir "timing_summary.txt"]
report_power -file [file join $artifacts_dir "power_report.txt"]

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
