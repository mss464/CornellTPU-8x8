################################################################################
# package_tpu_ip.tcl  (FIXED - copy-first approach)
#
# Strategy: physically copy ALL RTL files into ip_out_dir/src/ BEFORE calling
# ipx::package_project. This eliminates both:
#   (a) "outside project area" CRITICAL WARNINGs  (files are now inside)
#   (b) "unreferenced file not packaged" WARNINGs (all files are in src/)
#
# Usage:
#   vivado -mode batch -source ultra96-v2/package_tpu_ip.tcl -tclargs \
#       -ip_name cornell_tpu -part xczu3eg-sbva484-1-i \
#       -rtl_dir tensorcore -rtl_dir ultra96-v2/rtl \
#       -repo_out ultra96-v2/ip_repo
################################################################################

set ip_name    "cornell_tpu"
set part       "xczu3eg-sbva484-1-i"
set rtl_dirs   {}
set repo_out   ""
set ip_version "1.0"
set ip_vendor  "cornell.edu"
set ip_library "user"

proc parse_args {} {
    global argc argv ip_name part rtl_dirs repo_out ip_version ip_vendor ip_library
    for {set i 0} {$i < $argc} {incr i} {
        set arg [lindex $argv $i]
        switch -exact -- $arg {
            "-ip_name"    { incr i; set ip_name    [lindex $argv $i] }
            "-part"       { incr i; set part        [lindex $argv $i] }
            "-rtl_dir"    { incr i; lappend rtl_dirs [lindex $argv $i] }
            "-repo_out"   { incr i; set repo_out   [lindex $argv $i] }
            "-ip_version" { incr i; set ip_version [lindex $argv $i] }
            "-ip_vendor"  { incr i; set ip_vendor  [lindex $argv $i] }
            "-ip_library" { incr i; set ip_library [lindex $argv $i] }
            default       { puts "WARNING: Unknown argument: $arg" }
        }
    }
    if {[llength $rtl_dirs] == 0} { puts "ERROR: -rtl_dir required"; exit 1 }
    if {$repo_out eq ""}          { puts "ERROR: -repo_out required"; exit 1 }
}
parse_args

set norm_dirs {}
foreach d $rtl_dirs { lappend norm_dirs [file normalize $d] }
set rtl_dirs $norm_dirs
set repo_out [file normalize $repo_out]

puts "============================================================"
puts "TPU IP Packaging Script"
puts "IP Name:     $ip_name"
puts "IP Version:  $ip_version"
puts "Part:        $part"
puts "RTL Dirs:    $rtl_dirs"
puts "Output Repo: $repo_out"
puts "============================================================"

file mkdir $repo_out
set proj_dir [file normalize [file join [pwd] "pkg_${ip_name}_proj"]]
file delete -force $proj_dir

################################################################################
# Step 1: Collect RTL file lists (before creating project)
################################################################################
puts "\n>>> Step 1: Collecting RTL files..."

set v_files  {}
set sv_files {}
foreach rtl_dir $rtl_dirs {
    puts "  Scanning: $rtl_dir"
    set v_files  [concat $v_files  [glob -nocomplain -directory $rtl_dir *.v]]
    set sv_files [concat $sv_files [glob -nocomplain -directory $rtl_dir *.sv]]
}
set all_rtl_files [concat $v_files $sv_files]

if {[llength $all_rtl_files] == 0} {
    puts "ERROR: No RTL files found in: $rtl_dirs"
    exit 1
}
puts "  Found [llength $all_rtl_files] RTL file(s)"

################################################################################
# Step 2: Copy ALL RTL files into ip_out_dir/src/ FIRST
#
# This is the key fix. Vivado's IP packager requires all source files to live
# under the IP root directory. By copying them before packaging we avoid both
# the "outside project area" and "unreferenced file" warnings.
################################################################################
puts "\n>>> Step 2: Copying RTL files into IP src/ directory..."

set ip_out_dir [file normalize [file join $repo_out "${ip_name}_${ip_version}"]]
set ip_src_dir [file join $ip_out_dir "src"]
file delete -force $ip_out_dir
file mkdir $ip_src_dir

foreach f $all_rtl_files {
    set dst [file join $ip_src_dir [file tail $f]]
    file copy -force $f $dst
    puts "  Copied: [file tail $f]"
}
puts "  All RTL copied to: $ip_src_dir"

################################################################################
# Step 3: Create Vivado project pointing at the COPIES in src/
################################################################################
puts "\n>>> Step 3: Creating project..."
create_project pkg_${ip_name} $proj_dir -part $part -force
set_property target_language Verilog [current_project]
set_property verilog_define {TARGET_FPGA=1} [current_fileset]

# Add the copied files
set copied_sv {}
set copied_v  {}
foreach f $all_rtl_files {
    set dst [file join $ip_src_dir [file tail $f]]
    add_files -norecurse $dst
    if {[lsearch $sv_files $f] >= 0} {
        set_property file_type "SystemVerilog" [get_files $dst]
        lappend copied_sv $dst
    } else {
        lappend copied_v $dst
    }
    puts "  Added: [file tail $dst]"
}

################################################################################
# Step 4: Create BRAM IPs
################################################################################
puts "\n>>> Step 4: Creating BRAM IPs..."

puts "  blk_mem_gen_0 (Data BRAM 32-bit x 8192)..."
create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 \
    -module_name blk_mem_gen_0
set_property -dict [list \
    CONFIG.Memory_Type                                {True_Dual_Port_RAM} \
    CONFIG.Write_Width_A                              {32} \
    CONFIG.Write_Depth_A                              {8192} \
    CONFIG.Read_Width_A                               {32} \
    CONFIG.Write_Width_B                              {32} \
    CONFIG.Read_Width_B                               {32} \
    CONFIG.Enable_A                                   {Use_ENA_Pin} \
    CONFIG.Enable_B                                   {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {false} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {false} \
    CONFIG.Use_Byte_Write_Enable                      {false} \
    CONFIG.Byte_Size                                  {9} \
    CONFIG.Operating_Mode_A                           {WRITE_FIRST} \
    CONFIG.Operating_Mode_B                           {WRITE_FIRST} \
] [get_ips blk_mem_gen_0]
generate_target all [get_ips blk_mem_gen_0]
export_ip_user_files -of_objects [get_ips blk_mem_gen_0] -no_script -force

puts "  blk_mem_gen_1 (Instruction BRAM 64-bit x 256)..."
create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 \
    -module_name blk_mem_gen_1
set_property -dict [list \
    CONFIG.Memory_Type                                {True_Dual_Port_RAM} \
    CONFIG.Write_Width_A                              {64} \
    CONFIG.Write_Depth_A                              {256} \
    CONFIG.Read_Width_A                               {64} \
    CONFIG.Write_Width_B                              {64} \
    CONFIG.Read_Width_B                               {64} \
    CONFIG.Enable_A                                   {Use_ENA_Pin} \
    CONFIG.Enable_B                                   {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {false} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {false} \
    CONFIG.Use_Byte_Write_Enable                      {false} \
    CONFIG.Byte_Size                                  {9} \
    CONFIG.Operating_Mode_A                           {WRITE_FIRST} \
    CONFIG.Operating_Mode_B                           {WRITE_FIRST} \
] [get_ips blk_mem_gen_1]
generate_target all [get_ips blk_mem_gen_1]
export_ip_user_files -of_objects [get_ips blk_mem_gen_1] -no_script -force

puts "  blk_mem_gen_3 (L2 SRAM 32-bit x 32768)..."
create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 \
    -module_name blk_mem_gen_3
set_property -dict [list \
    CONFIG.Memory_Type                                {True_Dual_Port_RAM} \
    CONFIG.Write_Width_A                              {32} \
    CONFIG.Write_Depth_A                              {32768} \
    CONFIG.Read_Width_A                               {32} \
    CONFIG.Write_Width_B                              {32} \
    CONFIG.Read_Width_B                               {32} \
    CONFIG.Enable_A                                   {Use_ENA_Pin} \
    CONFIG.Enable_B                                   {Use_ENB_Pin} \
    CONFIG.Register_PortA_Output_of_Memory_Primitives {false} \
    CONFIG.Register_PortB_Output_of_Memory_Primitives {false} \
    CONFIG.Use_Byte_Write_Enable                      {false} \
    CONFIG.Byte_Size                                  {9} \
    CONFIG.Operating_Mode_A                           {WRITE_FIRST} \
    CONFIG.Operating_Mode_B                           {WRITE_FIRST} \
] [get_ips blk_mem_gen_3]
generate_target all [get_ips blk_mem_gen_3]
export_ip_user_files -of_objects [get_ips blk_mem_gen_3] -no_script -force
puts "  BRAM IPs created."

################################################################################
# Step 5: Set top and compile order
################################################################################
puts "\n>>> Step 5: Setting top module to 'tpu'..."
set_property top tpu [current_fileset]
update_compile_order -fileset sources_1

################################################################################
# Step 6: Package IP
# -import_files now works correctly because:
#   - All RTL already lives under ip_out_dir/src/  → no "outside project" errors
#   - -import_files copies the BRAM XCIs into the IP directory cleanly
#   - All RTL files in src/ are already referenced by the project hierarchy
#     so none should be marked "unreferenced"
################################################################################
puts "\n>>> Step 6: Packaging IP..."

ipx::package_project -root_dir $ip_out_dir -vendor $ip_vendor \
    -library $ip_library -taxonomy /UserIP -import_files -set_current true

set core [ipx::current_core]
set_property name                $ip_name                                         $core
set_property version             $ip_version                                      $core
set_property display_name        "Cornell TPU Accelerator"                        $core
set_property description         "TPU with AXI-Lite control and AXI-Stream data" $core
set_property vendor_display_name "Cornell University"                             $core
set_property company_url         "https://www.cornell.edu"                        $core

################################################################################
# Step 7: Catch any files still marked unreferenced and add them manually
################################################################################
puts "\n>>> Step 7: Verifying all files in synthesis group..."

set synth_group [ipx::get_file_groups xilinx_anylanguagesynthesis \
                    -of_objects $core -quiet]
if {$synth_group eq ""} {
    set synth_group [ipx::add_file_group -type synthesis {} $core]
    set_property name         "xilinx_anylanguagesynthesis" $synth_group
    set_property display_name "Synthesis Sources"           $synth_group
}

set n_added 0
foreach f [concat $copied_sv $copied_v] {
    set fname    [file tail $f]
    set rel_path "src/$fname"

    # Try both relative and absolute lookup
    set handle [ipx::get_files $rel_path -of_objects $synth_group -quiet]
    if {$handle eq ""} {
        set handle [ipx::get_files $f -of_objects $synth_group -quiet]
    }

    if {$handle ne ""} {
        puts "  OK: $fname"
        # Ensure define is set even on already-present files
        catch { set_property VERILOG_DEFINE {TARGET_FPGA=1} $handle }
    } else {
        puts "  Adding (was unreferenced): $fname"
        catch {
            ipx::add_file $rel_path $synth_group
            set handle [ipx::get_files $rel_path -of_objects $synth_group -quiet]
            if {$handle ne ""} {
                if {[lsearch $copied_sv $f] >= 0} {
                    set_property type systemVerilogSource $handle
                } else {
                    set_property type verilogSource $handle
                }
                catch { set_property VERILOG_DEFINE {TARGET_FPGA=1} $handle }
            }
        }
        incr n_added
    }
}
puts "  Files added manually: $n_added"

################################################################################
# Step 8: Set TARGET_FPGA define on ALL synthesis files
################################################################################
puts "\n>>> Step 8: Setting TARGET_FPGA define on synthesis files..."
foreach fg [ipx::get_file_groups xilinx_anylanguagesynthesis -of_objects $core] {
    foreach f [ipx::get_files -of_objects $fg] {
        set ftype [get_property TYPE $f]
        if {$ftype eq "systemVerilogSource" || $ftype eq "verilogSource"} {
            catch { set_property VERILOG_DEFINE {TARGET_FPGA=1} $f }
        }
    }
}

################################################################################
# Step 9: Verify AXI interfaces
################################################################################
puts "\n>>> Step 9: Verifying AXI interfaces..."
foreach req {s00_axi s00_axis m00_axis m_axi} {
    if {[llength [ipx::get_bus_interfaces $req -of_objects $core -quiet]] == 0} {
        puts "  WARNING: '$req' NOT found"
    } else {
        puts "  OK: $req"
    }
}

################################################################################
# Step 10: AXI-Lite memory map
################################################################################
puts "\n>>> Step 10: AXI-Lite memory map..."
set axi_lite [ipx::get_bus_interfaces s00_axi -of_objects $core -quiet]
if {$axi_lite ne "" && \
    [llength [ipx::get_memory_maps s00_axi -of_objects $core -quiet]] == 0} {
    ipx::add_memory_map s00_axi $core
    set_property slave_memory_map_ref s00_axi $axi_lite
    ipx::add_address_block reg0 [ipx::get_memory_maps s00_axi -of_objects $core]
    set ab [ipx::get_address_blocks reg0 \
                -of_objects [ipx::get_memory_maps s00_axi -of_objects $core]]
    set_property range 64 $ab
    set_property width 32 $ab
    puts "  Memory map: 64 bytes, 32-bit"
} else {
    puts "  Memory map already present (or s00_axi not found)"
}

################################################################################
# Step 11: Display names and Master Address Space
################################################################################
catch { set_property display_name "S00_AXI"  \
            [ipx::get_bus_interfaces s00_axi  -of_objects $core] }
catch { set_property display_name "S00_AXIS" \
            [ipx::get_bus_interfaces s00_axis -of_objects $core] }
catch { set_property display_name "M00_AXIS" \
            [ipx::get_bus_interfaces m00_axis -of_objects $core] }
catch { set_property display_name "M_AXI_MEM" \
            [ipx::get_bus_interfaces m_axi -of_objects $core] }
catch { set_property value 128 [ipx::get_bus_parameters DATA_WIDTH -of_objects [ipx::get_bus_interfaces m_axi -of_objects $core]] }

# Ensure m_axi has an address space (required for master interfaces)
set m_axi_if [ipx::get_bus_interfaces m_axi -of_objects $core -quiet]
if {$m_axi_if ne ""} {
    if {[llength [ipx::get_address_spaces m_axi -of_objects $core -quiet]] == 0} {
        ipx::add_address_space m_axi $core
        set as [ipx::get_address_spaces m_axi -of_objects $core]
        set_property range 4G $as
        set_property width 32 $as
        set_property master_address_space_ref m_axi $m_axi_if
        puts "  Added master address space for m_axi (4GB, 32-bit)"
    }
}

################################################################################
# Step 12: Finalise
################################################################################
puts "\n>>> Step 12: Finalising..."
ipx::create_xgui_files $core
ipx::update_checksums  $core
ipx::check_integrity   $core
ipx::save_core         $core

close_project
file delete -force $proj_dir

set n_src [llength [glob -nocomplain \
    [file join $ip_src_dir *.sv] [file join $ip_src_dir *.v]]]

set vlnv "${ip_vendor}:${ip_library}:${ip_name}:${ip_version}"
puts ""
puts "============================================================"
puts "IP PACKAGING COMPLETE"
puts "============================================================"
puts "IP Location : $ip_out_dir"
puts "VLNV        : $vlnv"
puts "src/ files  : $n_src"
puts "============================================================"
puts ""
puts "Verify with:"
puts "  ls $ip_src_dir"
puts ""
puts "To use in a Vivado project:"
puts "  set_property ip_repo_paths $repo_out \[current_project\]"
puts "  update_ip_catalog"
puts ""
exit 0