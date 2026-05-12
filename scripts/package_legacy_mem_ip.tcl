set ip_name     "tpu_top_v6"
set part        "xczu3eg-sbva484-1-i"
set rtl_dirs    {}
set repo_out    ""
set ip_version  "1.0"
set ip_vendor   "xilinx.com"
set ip_library  "user"

proc parse_args {} {
    global argc argv ip_name part rtl_dirs repo_out ip_version ip_vendor ip_library

    for {set i 0} {$i < $argc} {incr i} {
        set arg [lindex $argv $i]
        switch -exact -- $arg {
            "-ip_name"    { incr i; set ip_name [lindex $argv $i] }
            "-part"       { incr i; set part [lindex $argv $i] }
            "-rtl_dir"    { incr i; lappend rtl_dirs [lindex $argv $i] }
            "-repo_out"   { incr i; set repo_out [lindex $argv $i] }
            "-ip_version" { incr i; set ip_version [lindex $argv $i] }
            "-ip_vendor"  { incr i; set ip_vendor [lindex $argv $i] }
            "-ip_library" { incr i; set ip_library [lindex $argv $i] }
            "-help" {
                puts "Usage: vivado -mode batch -source scripts/package_legacy_mem_ip.tcl -tclargs -rtl_dir tpu_source_code -repo_out build/ip_repo"
                exit 0
            }
            default { puts "WARNING: Unknown argument: $arg" }
        }
    }

    if {[llength $rtl_dirs] == 0} { puts "ERROR: -rtl_dir required"; exit 1 }
    if {$repo_out eq ""} { puts "ERROR: -repo_out required"; exit 1 }
}

parse_args

set norm_dirs {}
foreach d $rtl_dirs { lappend norm_dirs [file normalize $d] }
set rtl_dirs $norm_dirs
set repo_out [file normalize $repo_out]

puts "============================================================"
puts "Legacy Memory Baseline IP Packaging"
puts "IP:       ${ip_vendor}:${ip_library}:${ip_name}:${ip_version}"
puts "Part:     $part"
puts "RTL Dirs: $rtl_dirs"
puts "Repo:     $repo_out"
puts "============================================================"

file mkdir $repo_out
set proj_dir [file normalize [file join [pwd] "pkg_${ip_name}_proj"]]
file delete -force $proj_dir

set all_rtl_files {}
foreach rtl_dir $rtl_dirs {
    foreach f [concat \
        [glob -nocomplain -directory $rtl_dir *.v] \
        [glob -nocomplain -directory $rtl_dir *.sv]] {
        if {[string first ":" [file tail $f]] >= 0} {
            puts "  Skipping sidecar file: [file tail $f]"
        } else {
            lappend all_rtl_files $f
        }
    }
}

if {[llength $all_rtl_files] == 0} {
    puts "ERROR: No RTL files found"
    exit 1
}

set ip_out_dir [file normalize [file join $repo_out "${ip_name}_${ip_version}"]]
set ip_src_dir [file join $ip_out_dir "src"]
file delete -force $ip_out_dir
file mkdir $ip_src_dir

puts "\n>>> Copying RTL into IP directory..."
foreach f $all_rtl_files {
    set dst [file join $ip_src_dir [file tail $f]]
    file copy -force $f $dst
    puts "  [file tail $f]"
}

puts "\n>>> Creating packaging project..."
create_project pkg_${ip_name} $proj_dir -part $part -force
set_property target_language Verilog [current_project]
set_property verilog_define {TARGET_FPGA=1} [current_fileset]

set copied_files {}
foreach f $all_rtl_files {
    set dst [file join $ip_src_dir [file tail $f]]
    add_files -norecurse $dst
    lappend copied_files $dst
    if {[string match "*.sv" [file tail $dst]]} {
        set_property file_type "SystemVerilog" [get_files $dst]
    }
}

puts "\n>>> Creating BRAM IPs..."
create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 -module_name blk_mem_gen_0
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
] [get_ips blk_mem_gen_0]
generate_target all [get_ips blk_mem_gen_0]
export_ip_user_files -of_objects [get_ips blk_mem_gen_0] -no_script -force

create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 -module_name blk_mem_gen_1
set_property -dict [list \
    CONFIG.Memory_Type {True_Dual_Port_RAM} \
    CONFIG.Write_Width_A {64} \
    CONFIG.Write_Depth_A {256} \
    CONFIG.Read_Width_A {64} \
    CONFIG.Write_Width_B {64} \
    CONFIG.Read_Width_B {64} \
    CONFIG.Enable_A {Use_ENA_Pin} \
    CONFIG.Enable_B {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {false} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {false} \
    CONFIG.Use_Byte_Write_Enable {false} \
    CONFIG.Byte_Size {9} \
    CONFIG.Operating_Mode_A {WRITE_FIRST} \
    CONFIG.Operating_Mode_B {WRITE_FIRST} \
] [get_ips blk_mem_gen_1]
generate_target all [get_ips blk_mem_gen_1]
export_ip_user_files -of_objects [get_ips blk_mem_gen_1] -no_script -force

puts "\n>>> Setting top and packaging IP..."
set_property top tpu_top_v6 [current_fileset]
update_compile_order -fileset sources_1

ipx::package_project -root_dir $ip_out_dir -vendor $ip_vendor \
    -library $ip_library -taxonomy /UserIP -import_files -set_current true

set core [ipx::current_core]
set_property name $ip_name $core
set_property version $ip_version $core
set_property display_name "Legacy Cornell TPU Memory Baseline" $core
set_property description "Legacy tpu_top_v6 baseline with AXI-Lite control and AXI-Stream DMA" $core

set synth_group [ipx::get_file_groups xilinx_anylanguagesynthesis -of_objects $core -quiet]
if {$synth_group eq ""} {
    set synth_group [ipx::add_file_group -type synthesis {} $core]
    set_property name "xilinx_anylanguagesynthesis" $synth_group
}

foreach f $copied_files {
    set rel_path "src/[file tail $f]"
    set handle [ipx::get_files $rel_path -of_objects $synth_group -quiet]
    if {$handle eq ""} {
        ipx::add_file $rel_path $synth_group
        set handle [ipx::get_files $rel_path -of_objects $synth_group -quiet]
    }
    if {$handle ne ""} {
        if {[string match "*.sv" [file tail $f]]} {
            set_property type systemVerilogSource $handle
        } else {
            set_property type verilogSource $handle
        }
        catch { set_property VERILOG_DEFINE {TARGET_FPGA=1} $handle }
    }
}

set axi_lite [ipx::get_bus_interfaces s00_axi -of_objects $core -quiet]
if {$axi_lite ne "" && [llength [ipx::get_memory_maps s00_axi -of_objects $core -quiet]] == 0} {
    ipx::add_memory_map s00_axi $core
    set_property slave_memory_map_ref s00_axi $axi_lite
    ipx::add_address_block reg0 [ipx::get_memory_maps s00_axi -of_objects $core]
    set ab [ipx::get_address_blocks reg0 -of_objects [ipx::get_memory_maps s00_axi -of_objects $core]]
    set_property range 4096 $ab
    set_property width 32 $ab
}

catch { set_property display_name "S00_AXI" [ipx::get_bus_interfaces s00_axi -of_objects $core] }
catch { set_property display_name "S00_AXIS" [ipx::get_bus_interfaces s00_axis -of_objects $core] }
catch { set_property display_name "M00_AXIS" [ipx::get_bus_interfaces m00_axis -of_objects $core] }

ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity $core
ipx::save_core $core

close_project
file delete -force $proj_dir

puts ""
puts "IP PACKAGING COMPLETE: $ip_out_dir"
exit 0
