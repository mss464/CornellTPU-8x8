set proj_name    "legacy_mem_system"
set part         "xczu3eg-sbva484-1-i"
set ip_repo_path ""
set out_dir      ""
set bd_name      "design_1"

proc parse_args {} {
    global argc argv proj_name part ip_repo_path out_dir bd_name

    for {set i 0} {$i < $argc} {incr i} {
        set arg [lindex $argv $i]
        switch -exact -- $arg {
            "-proj_name"    { incr i; set proj_name [lindex $argv $i] }
            "-part"         { incr i; set part [lindex $argv $i] }
            "-ip_repo_path" { incr i; set ip_repo_path [lindex $argv $i] }
            "-out_dir"      { incr i; set out_dir [lindex $argv $i] }
            "-bd_name"      { incr i; set bd_name [lindex $argv $i] }
            "-help" {
                puts "Usage: vivado -mode batch -source scripts/build_legacy_mem_bitstream.tcl -tclargs -ip_repo_path build/ip_repo -out_dir build"
                exit 0
            }
            default { puts "WARNING: Unknown argument: $arg" }
        }
    }

    if {$ip_repo_path eq ""} { puts "ERROR: -ip_repo_path required"; exit 1 }
    if {$out_dir eq ""} { puts "ERROR: -out_dir required"; exit 1 }
}

parse_args

set ip_repo_path [file normalize $ip_repo_path]
set out_dir [file normalize $out_dir]
set proj_dir [file join $out_dir $proj_name]
set artifacts_dir [file join $out_dir "artifacts"]
file mkdir $out_dir
file mkdir $artifacts_dir

puts "============================================================"
puts "Legacy Memory Baseline Bitstream Build"
puts "Project: $proj_name"
puts "Part:    $part"
puts "IP Repo: $ip_repo_path"
puts "Output:  $out_dir"
puts "BD:      $bd_name"
puts "============================================================"

if {[file exists $proj_dir]} {
    file delete -force $proj_dir
}
create_project $proj_name $proj_dir -part $part -force
set_property verilog_define {TARGET_FPGA=1} [current_fileset]

set_property ip_repo_paths $ip_repo_path [current_project]
update_ip_catalog -rebuild

set tpu_ip [get_ipdefs -filter "NAME == tpu_top_v6"]
if {$tpu_ip eq ""} {
    set tpu_ip [get_ipdefs -filter "NAME =~ *tpu_top_v6*"]
}
if {$tpu_ip eq ""} {
    puts "ERROR: tpu_top_v6 IP not found in $ip_repo_path"
    foreach ip [get_ipdefs] { puts "  $ip" }
    close_project
    exit 1
}

create_bd_design $bd_name

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 zynq_ultra_ps_e_0]
set_property -dict [list \
    CONFIG.PSU__USE__M_AXI_GP0 {0} \
    CONFIG.PSU__USE__M_AXI_GP1 {0} \
    CONFIG.PSU__USE__M_AXI_GP2 {1} \
    CONFIG.PSU__USE__S_AXI_GP0 {1} \
    CONFIG.PSU__USE__S_AXI_GP2 {0} \
    CONFIG.PSU__USE__S_AXI_GP3 {0} \
    CONFIG.PSU__USE__S_AXI_GP4 {0} \
    CONFIG.PSU__USE__S_AXI_GP5 {0} \
    CONFIG.PSU__USE__S_AXI_GP6 {0} \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {50} \
] $ps

set ps_reset [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 proc_sys_reset_0]
set_property -dict [list CONFIG.C_EXT_RESET_HIGH {0}] $ps_reset

set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0]
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

set tpu [create_bd_cell -type ip -vlnv $tpu_ip tpu_top_v6_0]

set axi_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_interconnect_0]
set_property -dict [list CONFIG.NUM_MI {2} CONFIG.NUM_SI {1}] $axi_ic

set axi_smc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_smc_1]
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1}] $axi_smc

connect_bd_intf_net [get_bd_intf_pins zynq_ultra_ps_e_0/M_AXI_HPM0_LPD] \
                    [get_bd_intf_pins axi_interconnect_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] \
                    [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M01_AXI] \
                    [get_bd_intf_pins tpu_top_v6_0/s00_axi]

connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] \
                    [get_bd_intf_pins tpu_top_v6_0/s00_axis]
connect_bd_intf_net [get_bd_intf_pins tpu_top_v6_0/m00_axis] \
                    [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]

connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_MM2S] \
                    [get_bd_intf_pins axi_smc_1/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXI_S2MM] \
                    [get_bd_intf_pins axi_smc_1/S01_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_smc_1/M00_AXI] \
                    [get_bd_intf_pins zynq_ultra_ps_e_0/S_AXI_HPC0_FPD]

set pl_clk [get_bd_pins zynq_ultra_ps_e_0/pl_clk0]
connect_bd_net $pl_clk [get_bd_pins proc_sys_reset_0/slowest_sync_clk]
connect_bd_net $pl_clk [get_bd_pins zynq_ultra_ps_e_0/maxihpm0_lpd_aclk]
connect_bd_net $pl_clk [get_bd_pins zynq_ultra_ps_e_0/saxihpc0_fpd_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/s_axi_lite_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/m_axi_mm2s_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_dma_0/m_axi_s2mm_aclk]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/S00_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/M00_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_interconnect_0/M01_ACLK]
connect_bd_net $pl_clk [get_bd_pins axi_smc_1/aclk]
connect_bd_net $pl_clk [get_bd_pins tpu_top_v6_0/s00_axi_aclk]
connect_bd_net $pl_clk [get_bd_pins tpu_top_v6_0/s00_axis_aclk]
connect_bd_net $pl_clk [get_bd_pins tpu_top_v6_0/m00_axis_aclk]

connect_bd_net [get_bd_pins zynq_ultra_ps_e_0/pl_resetn0] [get_bd_pins proc_sys_reset_0/ext_reset_in]
set ic_resetn [get_bd_pins proc_sys_reset_0/interconnect_aresetn]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/S00_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/M00_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_interconnect_0/M01_ARESETN]
connect_bd_net $ic_resetn [get_bd_pins axi_smc_1/aresetn]
set periph_resetn [get_bd_pins proc_sys_reset_0/peripheral_aresetn]
connect_bd_net $periph_resetn [get_bd_pins axi_dma_0/axi_resetn]
connect_bd_net $periph_resetn [get_bd_pins tpu_top_v6_0/s00_axi_aresetn]
connect_bd_net $periph_resetn [get_bd_pins tpu_top_v6_0/s00_axis_aresetn]
connect_bd_net $periph_resetn [get_bd_pins tpu_top_v6_0/m00_axis_aresetn]

assign_bd_address -target_address_space /zynq_ultra_ps_e_0/Data \
    [get_bd_addr_segs axi_dma_0/S_AXI_LITE/Reg] -offset 0x80000000 -range 64K -force
assign_bd_address -target_address_space /zynq_ultra_ps_e_0/Data \
    [get_bd_addr_segs tpu_top_v6_0/s00_axi/reg0] -offset 0x80010000 -range 4K -force
assign_bd_address -target_address_space /axi_dma_0/Data_MM2S \
    [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_DDR_LOW] -force
assign_bd_address -target_address_space /axi_dma_0/Data_S2MM \
    [get_bd_addr_segs zynq_ultra_ps_e_0/SAXIGP0/HPC0_DDR_LOW] -force

validate_bd_design
save_bd_design

set bd_file [get_files [file join $proj_dir $proj_name.srcs sources_1 bd $bd_name $bd_name.bd]]
generate_target all $bd_file

set wrapper [make_wrapper -files $bd_file -top]
add_files -norecurse $wrapper
set_property top ${bd_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
set synth_status [get_property STATUS [get_runs synth_1]]
puts "Synthesis status: $synth_status"
if {$synth_status ne "synth_design Complete!"} {
    puts "ERROR: Synthesis failed"
    close_project
    exit 1
}

launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
set impl_status [get_property STATUS [get_runs impl_1]]
puts "Implementation status: $impl_status"
if {[string match "*ERROR*" $impl_status] || [string match "*failed*" $impl_status]} {
    puts "ERROR: Implementation failed"
    close_project
    exit 1
}

set bit_file [glob -nocomplain [file join $proj_dir $proj_name.runs impl_1 *.bit]]
if {$bit_file eq ""} {
    puts "ERROR: Bitstream not found"
    close_project
    exit 1
}
file copy -force [lindex $bit_file 0] [file join $artifacts_dir "${bd_name}.bit"]

set hwh_file [glob -nocomplain [file join $proj_dir $proj_name.gen sources_1 bd $bd_name hw_handoff *.hwh]]
if {$hwh_file eq ""} {
    puts "ERROR: HWH not found"
    close_project
    exit 1
}
file copy -force [lindex $hwh_file 0] [file join $artifacts_dir "${bd_name}.hwh"]

open_run impl_1
report_utilization -file [file join $artifacts_dir utilization_report.txt]
report_timing_summary -file [file join $artifacts_dir timing_summary.txt]

close_project
puts "BUILD COMPLETE: $artifacts_dir"
exit 0
