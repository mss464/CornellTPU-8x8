################################################################################
# package_compute_tile_ip.tcl - Compute_Tile IP Packaging
#
# Packages the portable Compute_Tile into a Vivado IP (no board-specific wrappers).
# Top module: compute_core
#
# Usage:
#   vivado -mode batch -source package_compute_tile_ip.tcl -tclargs \
#       -part xczu3eg-sbva484-1-i \
#       -out ip_repo
################################################################################

# Defaults
set part        "xczu3eg-sbva484-1-i"
set in_dir      "src/compute_tile"
set out_dir     "ip_repo"
set ip_name     "compute_tile"
set ip_version  "1.0"
set ip_vendor   "minitpu_team"

# Parse args
for {set i 0} {$i < $argc} {incr i} {
    set arg [lindex $argv $i]
    switch -exact -- $arg {
        "-part"       { incr i; set part [lindex $argv $i] }
        "-out"        { incr i; set out_dir [lindex $argv $i] }
        "-ip_name"    { incr i; set ip_name [lindex $argv $i] }
        "-ip_version" { incr i; set ip_version [lindex $argv $i] }
        "-in"         { incr i; set in_dir [lindex $argv $i] }
        "-help" {
            puts "Usage: vivado -mode batch -source package_ip.tcl -tclargs <options>"
            puts "  -part <part>        FPGA part (default: xczu3eg-sbva484-1-i)"
            puts "  -in <dir>           Input directory (default: compute_tile)"
            puts "  -out <dir>          Output directory (default: ip_repo)"
            puts "  -ip_name <name>     IP name (default: compute_tile)"
            puts "  -ip_version <ver>   IP version (default: 1.0)"
            exit 0
        }
    }
}

set script_dir [file dirname [file normalize [info script]]]
set in_dir [file normalize $in_dir]
set out_dir [file normalize $out_dir]

puts "============================================================"
puts "Compute_Tile IP Packaging"
puts "============================================================"
puts "Part:    $part"
puts "Output:  $out_dir"
puts "IP:      ${ip_vendor}:user:${ip_name}:${ip_version}"
puts "============================================================"

# Create temp project
set proj_dir [file join [pwd] "pkg_${ip_name}_tmp"]
file delete -force $proj_dir
create_project pkg_${ip_name} $proj_dir -part $part -force

# Add RTL files
puts "\n>>> Adding RTL files..."
set sv_files [glob -directory [file normalize $in_dir] *.sv]
foreach f $sv_files {
    puts "  [file tail $f]"
    add_files -norecurse $f
    set_property file_type "SystemVerilog" [get_files $f]
}

# Set top module
puts "\n>>> Setting top module: compute_tile"
set_property top compute_tile [current_fileset]
update_compile_order -fileset sources_1

# Package IP
puts "\n>>> Packaging IP..."
set ip_out [file join $out_dir "${ip_name}_${ip_version}"]
file mkdir $ip_out

ipx::package_project -root_dir $ip_out -vendor $ip_vendor -library user \
    -taxonomy /UserIP -import_files -set_current true

set core [ipx::current_core]
set_property name $ip_name $core
set_property version $ip_version $core
set_property display_name "TPU Compute Tile" $core
set_property description "Portable Compute_Tile with systolic array and VPU" $core

# Finalize
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity $core
ipx::save_core $core

close_project
file delete -force $proj_dir

puts ""
puts "============================================================"
puts "IP packaged: $ip_out"
puts "VLNV: ${ip_vendor}:user:${ip_name}:${ip_version}"
puts "============================================================"

exit 0
